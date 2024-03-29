from contextlib import asynccontextmanager
from typing import Any

import click
import socketio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pylsl import resolve_streams

from app.devices.eeg.decoder import Decoder, measure_baseline
from app.devices.eeg.models.threshold_model import ThresholdModel as Model
from app.devices.eeg.recorder import Recorder
from app.devices.utils.networking import create_observable_from_stream_inlet, get_stream_inlet

# from app.devices.eeg.models.threshold_model import ThresholdDiffModel as Model


@click.command()
@click.option("--env-ip", "-e", default="localhost", type=str, help="IP address of the environment server")
@click.option("--input", "-i", default="EEG", type=click.Choice(["EEG", "Audio"]), help="Input type")
@click.option("--no-decode", flag_value=True, type=bool, help="Disable decoding")
@click.option("--no-record", flag_value=True, type=bool, help="Disable recording")
# options for decoder
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
    default=2.0,
    type=click.FloatRange(min=0),
    help="Duration before baseline measurement in seconds",
)
@click.option("--thres", "-t", default=12.0, type=click.FloatRange(min=0), help="Threshold for channel activation")
@click.option(
    "--window-duration",
    "-wdur",
    default=0.1,  # long window can cause delay
    type=click.FloatRange(min=0),
    help="Window duration in seconds",
)
# options for recorder
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
    window_duration,
    record_path,
    record_interval,
) -> None:
    host = "localhost"
    port = 8002
    origins = [
        f"http://{host}:{port}",  # eeg server (this app)
        f"https://{env_ip}:8000",  # environment server
    ]
    sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=origins)
    num_clients = 0

    runners: list[Any] = []

    @sio.event
    async def connect(sid: str, environ: dict) -> None:
        """Event handler for the "connect" event, which happens when a client is connected."""

        nonlocal num_clients
        num_clients += 1
        print("Client connected:", sid)

    @sio.event
    async def disconnect(sid) -> None:
        """Event handler for the "disconnect" event, which happens when a client is disconnected."""

        nonlocal num_clients
        num_clients -= 1
        print("Client disconnected:", sid)

        # Stop the runners if no clients are connected
        if num_clients == 0:
            # Wait a bit for reconnection (skip for now)
            # reconnect_wait_time = 5
            # print(f"Stop runners if no clients are connected in {reconnect_wait_time} seconds.")
            # await asyncio.sleep(reconnect_wait_time)

            for runner in runners:
                if runner.is_running:
                    runner.stop()
            runners.clear()

    @sio.on("init")
    async def init(sid: str, data: dict) -> None:
        """Event handler for the "init" event, which happens when the client sends initialization info
        after connecting.
        """

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

            model = Model(num_classes, thres, baselines)
            window_size = int(input_freq * window_duration)
            # window_step = window_size // 2
            window_step = None  # no overlap
            decoder = Decoder(input_observable, model, window_size, window_step)
            decoder.set_socket(sio)
            runners.append(decoder)

        # Start the runners
        for runner in runners:
            runner.start()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Code executed at server startup and shutdown."""
        yield
        # post process
        for runner in runners:
            if runner.is_running:
                runner.stop()
        # TODO: close stream inlets?

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
