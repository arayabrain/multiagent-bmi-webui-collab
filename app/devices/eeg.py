"""
- Receives EEG data from LSL Stream
- Decodes EEG data
- Sends decoding result to the server via ZMQ
"""

import asyncio
import struct
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

from app.utils.networking import create_observable_from_stream_inlet, get_stream_inlet

window_duration = 1  # seconds

origins = [
    "http://localhost:8002",  # socket.io server (this app)
    "http://10.10.0.137:8000",  # browser client  # TODO: hard-coded
]
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=origins)
num_clients = 0


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
    ) -> tuple[int, np.ndarray]:
        norm_data = (data - baselines["average"]) / baselines["rms"]
        rms = root_mean_square(norm_data)
        print(f"channel intensity: {[f'{r:.2f}' for r in rms]}")

        if len(rms) < num_classes:
            # zero-padding at the end
            rms = np.pad(rms, (0, num_classes - len(rms)))
        elif len(rms) > num_classes:
            # truncate
            rms = rms[:num_classes]

        max_ch = int(np.argmax(rms))
        if rms[max_ch] > thres:
            command = max_ch + 1  # 1-indexed channel number
        else:
            command = 0  # zero command
        return command, rms  # rms as likelihoods

    return model


def _extract_buffer(buf: list) -> tuple:
    data, timestamps = zip(*buf)
    data = np.stack(data).astype(float)  # (time, channels)  # TODO: float32 or 64?
    return data, timestamps


class Decoder:
    def __init__(self, model, input_observable, window_size, window_step):
        self.model = model
        self.input_observable = input_observable
        self.window_size = window_size
        self.window_step = window_step
        self.subscription = None
        self.is_running = False
        self.loop = asyncio.get_event_loop()

    def start(self):
        if self.is_running:
            print("Decoder is already running.")
            return

        self.subscription = self.input_observable.pipe(
            ops.buffer_with_count(self.window_size, self.window_step),  # list of (time, channels)
            ops.map(lambda buf: _extract_buffer(buf)[0]),  # (time, channels)
            ops.map(self._decode),
        ).subscribe(
            on_next=lambda data: self.loop.create_task(self._publish(*data)),
            on_completed=self.stop,
        )
        self.is_running = True

    def _decode(self, data: np.ndarray):
        return self.model(data)

    async def _publish(self, command: int, likelihoods: np.ndarray):
        print(f"EEG command: {command}, likelihoods: {likelihoods}")
        # command: 8-bit unsigned integer, likelihoods: 32-bit float, little-endian
        bytes = struct.pack("<B", command) + likelihoods.astype("<f4").tobytes()
        await sio.emit("eeg", bytes)

    def stop(self):
        print("Decoder stopped.")
        if self.subscription:
            self.subscription.dispose()
        self.is_running = False


def measure_baseline(
    input_observable,
    baseline_duration,
    baseline_ready_duration,
    input_freq,
):
    baselines = None
    baseline_ready = threading.Event()

    def set_baseline(data: np.ndarray):
        nonlocal baselines
        baselines = {
            "average": np.mean(data, axis=0),
            "rms": root_mean_square(data),
        }
        baseline_ready.set()

    # prompt user to keep still
    click.confirm(
        f"\nPreparing to measure the baseline. Press Enter, then relax and stay still."
        f"\nMeasurement will start in {baseline_ready_duration}s and will continue for {baseline_duration}s.",
        default=True,
    )
    # TODO
    # if not confirm:
    # return

    print(f"Starting baseline measurement in {baseline_ready_duration}s...")
    time.sleep(baseline_ready_duration)

    print("Measuring baseline...")
    baseline_subscription = input_observable.pipe(
        ops.buffer_with_count(int(baseline_duration * input_freq)),
        ops.take(1),  # take only the first buffer
        ops.map(lambda buf: _extract_buffer(buf)[0]),  # (time, channels)
    ).subscribe(
        on_next=set_baseline,
        on_completed=lambda: print("Baseline measurement completed."),
    )

    baseline_ready.wait()
    baseline_subscription.dispose()

    print(f"Average: {baselines['average']}")
    print(f"Root mean square: {baselines['rms']}\n")

    return baselines


class Recorder:
    def __init__(self, input_observable, input_nch, save_path="logs/data.hdf5", chunk_size=5000):
        self.input_observable = input_observable
        self.input_nch = input_nch
        self.chunk_size = chunk_size
        self.save_path = Path(__file__).parents[2] / save_path  # relative to the workspace root
        self.subscription = None
        self.is_running = False
        self.start_time = None

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

        with h5py.File(self.save_path, "a") as f:
            f["data"].resize(f["data"].shape[0] + size, axis=0)
            f["data"][-size:] = data
            f["timestamps"].resize(f["timestamps"].shape[0] + size, axis=0)
            f["timestamps"][-size:] = timestamps

        print(f"\r{elapsed_time:.1f}s: recorded {size} samples", end="")

    def stop(self):
        print("Recorder stopped.")
        print(f"Save path: {self.save_path}")
        if self.subscription:
            self.subscription.dispose()
        self.is_running = False


@click.command()
@click.option("--input", default="EEG", type=click.Choice(["EEG", "Audio"]), help="Input type")
@click.option("--mode", default="decode", type=click.Choice(["decode", "record"]), help="Decode or record EEG data")
# decoder only
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
@click.option("--record-path", default="logs/data.hdf5", type=click.Path(), help="Path to save recorded data")
@click.option("--record-interval", default=5.0, type=click.FloatRange(min=0), help="Recording interval in seconds")
def main(input, mode, baseline_duration, baseline_ready_duration, thres, record_path, record_interval):
    runner = None

    @sio.event
    async def connect(sid, environ):
        global num_clients
        num_clients += 1
        print("Client connected:", sid)
        await sio.emit("init", {"threshold": thres}, to=sid)

    @sio.event
    async def disconnect(sid):
        global num_clients
        num_clients -= 1
        print("Client disconnected:", sid)

        # Stop the runner if no clients are connected
        # await asyncio.sleep(reconnect_wait_time)  # TODO
        if num_clients == 0 and runner and runner.is_running:
            runner.stop()

    @sio.on("init")
    async def init(sid, data):
        print(f"Received initialization info: {data}")
        num_classes = data["numClasses"]

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

        nonlocal runner
        if mode == "decode":
            baselines = measure_baseline(input_observable, baseline_duration, baseline_ready_duration, input_freq)

            model = get_model(num_classes, thres, baselines)
            window_size = input_freq * window_duration
            window_step = window_size // 2
            runner = Decoder(model, input_observable, window_size, window_step)
        elif mode == "record":
            chunk_size = input_freq * record_interval
            runner = Recorder(input_observable, input_nch, save_path=record_path, chunk_size=chunk_size)

        runner.start()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        if runner and runner.is_running:
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
    uvicorn.run(socket_app, host="localhost", port=8002)


if __name__ == "__main__":
    main()
