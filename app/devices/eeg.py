"""
- Receives EEG data from LSL Stream
- Decodes EEG data
- Sends decoding result to the server via ZMQ
"""

import asyncio
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import click
import h5py
import numpy as np
import socketio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pylsl import resolve_streams
from reactivex import operators as ops

from app.devices.utils import array2str
from app.utils.networking import create_observable_from_stream_inlet, get_stream_inlet

window_duration = 1  # seconds
reconnect_wait_time = 5


def root_mean_square(data: np.ndarray) -> np.ndarray:
    """Root mean square of each channel in the data.
    Args:
        data: (time, channels)
    Returns:
        rms: (channels,)
    """
    return np.sqrt(np.mean(np.square(data), axis=0))


def get_model(num_classes: int, thres: float, baselines: dict):
    def model(
        data: np.ndarray,  # (time, channels)
    ) -> tuple[int | None, np.ndarray]:
        norm_data = (data - baselines["average"]) / baselines["rms"]
        rms = root_mean_square(norm_data)

        if len(rms) < num_classes:
            # zero-padding at the end
            rms = np.pad(rms, (0, num_classes - len(rms)))
        elif len(rms) > num_classes:
            # truncate
            rms = rms[:num_classes]

        max_ch = int(np.argmax(rms))
        if rms[max_ch] > thres:
            command = max_ch  # channel index
        else:
            command = None  # no command
        return command, rms  # rms as likelihoods

    return model


def _extract_buffer(buf: list) -> tuple:
    data, timestamps = zip(*buf)
    data = np.stack(data).astype(float)  # (time, channels)  # TODO: float32 or 64?
    # TODO: bottleneck?
    return data, timestamps


class Decoder:
    def __init__(
        self,
        input_observable,
        model,
        window_size,
        window_step,
    ):
        self.input_observable = input_observable
        self.subscription = None
        self.is_running = False

        self.model = model
        self.window_size = window_size
        self.window_step = window_step
        self.loop = asyncio.get_event_loop()
        self.sio = None

    def set_socket(self, sio):
        self.sio = sio

    def start(self):
        if self.is_running:
            print("Decoder is already running.")
            return

        self.subscription = self.input_observable.pipe(
            ops.buffer_with_count(self.window_size, self.window_step),  # list of (time, channels)
            ops.map(lambda buf: _extract_buffer(buf)[0]),  # (time, channels)
            ops.map(self._decode),
        ).subscribe(
            on_next=self._publish,
            on_completed=self.stop,
        )
        self.is_running = True

    def _decode(self, data: np.ndarray):
        return self.model(data)

    def _publish(self, data: tuple[int | None, np.ndarray]):
        if self.loop.is_closed():
            return

        command, likelihoods = data

        async def emit(command: int | None, likelihoods: np.ndarray):
            await self.sio.emit("eeg", {"command": command, "likelihoods": likelihoods.tolist()})

        self.loop.create_task(emit(command, likelihoods))

        command_str = f"{command:>4}" if command is not None else "None"
        likelihoods_str = array2str(likelihoods)
        print(f"EEG command: {command_str}, likelihoods: {likelihoods_str}")

    def stop(self):
        if self.subscription is not None:
            self.subscription.dispose()
        self.is_running = False
        print("Decoder stopped.")


def measure_baseline(
    input_observable,
    baseline_duration,
    baseline_ready_duration,
    input_freq,
    auto_start=False,
):
    baselines = None
    baseline_ready = threading.Event()

    def set_baseline(data: np.ndarray):
        nonlocal baselines
        baselines = {
            "average": np.mean(data, axis=0),
            "rms": root_mean_square(data),
        }

        print(f"Average: {array2str(baselines['average'])}")
        print(f"Root mean square: {array2str(baselines['rms'])}")

        baseline_ready.set()

    # prompt user to keep still
    confirm = auto_start or click.confirm(
        f"\nPreparing to measure the baseline. Press Enter, then relax and stay still."
        f"\nMeasurement will start in {baseline_ready_duration}s and will continue for {baseline_duration}s.",
        default=True,
    )
    if not confirm:
        print("Baseline measurement cancelled. Using average=0, rms=1 as default.")
        return {"average": 0, "rms": 1}

    print(f"Starting baseline measurement in {baseline_ready_duration}s...")
    time.sleep(baseline_ready_duration)

    print("Measuring baseline...")
    baseline_subscription = input_observable.pipe(
        ops.buffer_with_count(int(baseline_duration * input_freq)),
        ops.take(1),  # take only the first buffer
        ops.map(lambda buf: _extract_buffer(buf)[0]),  # (time, channels)
    ).subscribe(
        on_next=set_baseline,
        on_completed=lambda: print("Baseline measurement completed.\n"),
    )

    baseline_ready.wait()
    baseline_subscription.dispose()

    return baselines


class Recorder:
    def __init__(
        self,
        input_observable,
        input_nch,
        save_path,
        chunk_size=5000,
    ):
        self.input_observable = input_observable
        self.subscription = None
        self.is_running = False

        self.input_nch = input_nch
        self.chunk_size = chunk_size
        self.start_time = None

        if Path(save_path).is_absolute():
            self.save_path = Path(save_path)
        else:
            self.save_path = Path(__file__).parents[2] / save_path  # relative to the workspace root

    def start(self):
        if self.save_path.exists():
            print(f"Appending to existing file: {self.save_path}")
        else:
            print(f"Creating new file: {self.save_path}")
            self.save_path.parent.mkdir(parents=True, exist_ok=True)
        with h5py.File(self.save_path, "a") as f:
            if "data" not in f:
                f.create_dataset("data", (0, self.input_nch), maxshape=(None, self.input_nch), dtype="f", chunks=True)
            if "timestamps" not in f:
                f.create_dataset("timestamps", (0,), maxshape=(None,), dtype="f", chunks=True)

        self.start_time = time.time()
        self.is_running = True

        self.subscription = self.input_observable.pipe(
            ops.buffer_with_count(self.chunk_size),
        ).subscribe(
            on_next=self._save,
            on_completed=self.stop,
        )

    def _save(self, buf: list):
        elapsed_time = time.time() - self.start_time
        data, timestamps = _extract_buffer(buf)
        size = data.shape[0]

        # TODO: save as xdf?
        with h5py.File(self.save_path, "a") as f:
            f["data"].resize(f["data"].shape[0] + size, axis=0)
            f["data"][-size:] = data
            f["timestamps"].resize(f["timestamps"].shape[0] + size, axis=0)
            f["timestamps"][-size:] = timestamps

        print(f"{elapsed_time:.1f}s: recorded {size} samples")

    def stop(self):
        if self.subscription is not None:
            self.subscription.dispose()
        self.is_running = False
        print("Recorder stopped.")
        print(f"Save path: {self.save_path}")


@click.command()
@click.option("--env-ip", "-e", default="localhost", type=str, help="IP address of the environment server")
@click.option("--input", "-i", default="EEG", type=click.Choice(["EEG", "Audio"]), help="Input type")
@click.option("--no-decode", flag_value=True, type=bool, help="Disable decoding")
@click.option("--no-record", flag_value=True, type=bool, help="Disable recording")
# decoder only
@click.option("--auto-baseline", flag_value=True, help="Automatically start baseline measurement")
@click.option(
    "--baseline-duration",
    "-bdur",
    default=5.0,
    type=click.FloatRange(min=0),
    help="Baseline measurement duration in seconds",
)
@click.option(
    "--baseline-ready-duration",
    "-rdur",
    default=5.0,
    type=click.FloatRange(min=0),
    help="Duration before baseline measurement in seconds",
)
@click.option("--thres", "-t", default=15.0, type=click.FloatRange(min=0), help="Threshold for channel activation")
# recorder only
@click.option("--record-path", "-p", default="logs/data.hdf5", type=click.Path(), help="Path to save recorded data")
@click.option("--record-interval", default=5.0, type=click.FloatRange(min=0), help="Recording interval in seconds")
def main(
    env_ip,
    input,
    no_decode,
    no_record,
    auto_baseline,
    baseline_duration,
    baseline_ready_duration,
    thres,
    record_path,
    record_interval,
):
    host = "localhost"
    port = 8002
    origins = [
        f"http://{host}:{port}",  # eeg server (this app)
        f"https://{env_ip}:8000",  # environment server
    ]
    sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=origins)
    num_clients = 0

    runners = []

    @sio.event
    async def connect(sid, environ):
        nonlocal num_clients
        num_clients += 1
        print("Client connected:", sid)
        await sio.emit("init", {"threshold": thres}, to=sid)

    @sio.event
    async def disconnect(sid):
        nonlocal num_clients
        num_clients -= 1
        print("Client disconnected:", sid)

        # Stop the runners if no clients are connected
        if num_clients == 0:
            # Wait a bit for reconnection (skip for now)
            # print(f"Stop runners if no clients are connected in {reconnect_wait_time} seconds.")
            # await asyncio.sleep(reconnect_wait_time)

            for runner in runners:
                if runner.is_running:
                    runner.stop()
            runners.clear()

    @sio.on("init")
    async def init(sid, data):
        print(f"Received initialization info: {data}")
        num_classes = data["numClasses"]

        if len(runners) > 0:
            # if the runners are already set up, do nothing
            print("Runners are already set up. Use the existing runners.")
            return

        # Create stream inlets
        while True:
            try:
                stream_infos = resolve_streams(wait_time=1)
                input_inlet = get_stream_inlet(stream_infos, type=input)  # TODO: name
                input_freq = round(input_inlet.info().nominal_srate())
                input_nch = input_inlet.info().channel_count()
                print(f"Input stream {input_inlet.info().name()}: {input_freq} Hz")
                break
            except LookupError:  # Try again if get_stream_inlet fails
                pass

        # Create observables and set up processing pipeline using Rx
        input_observable = create_observable_from_stream_inlet(input_inlet)

        runners.clear()
        if not no_record:
            chunk_size = input_freq * record_interval
            recorder = Recorder(input_observable, input_nch, save_path=record_path, chunk_size=chunk_size)
            runners.append(recorder)
        if not no_decode:
            baselines = measure_baseline(
                input_observable, baseline_duration, baseline_ready_duration, input_freq, auto_start=auto_baseline
            )

            model = get_model(num_classes, thres, baselines)
            window_size = input_freq * window_duration
            window_step = window_size // 2
            decoder = Decoder(input_observable, model, window_size, window_step)
            decoder.set_socket(sio)
            runners.append(decoder)

        # Start the runners
        for runner in runners:
            runner.start()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        for runner in runners:
            if runner.is_running:
                runner.stop()

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    socket_app = socketio.ASGIApp(sio, other_asgi_app=app)

    # Start the server
    uvicorn.run(socket_app, host=host, port=port)


if __name__ == "__main__":
    main()
