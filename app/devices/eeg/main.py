import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import click
import numpy as np
import socketio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pylsl import local_clock, resolve_streams

from app.devices.eeg.decoder import Decoder, measure_baseline
from app.devices.eeg.models.threshold_model import ThresholdModel as Model
from app.devices.eeg.recorder import Recorder
from app.devices.utils.networking import create_observable_from_stream_inlet, get_stream_inlet

# from app.devices.eeg.models.threshold_model import ThresholdDiffModel as Model

num_rtt_measurements = 10


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
@click.option("--username", "-u", default="noname", type=str, help="Username")
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
    username,
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
    ref_time_browser = None

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
            # measure round-trip time for data collection
            async def measure_rtt():
                start_time = time.time()
                await sio.call("ping", to=sid)
                rtt = (time.time() - start_time) * 1000  # msec
                return rtt

            rtts = np.array([await measure_rtt() for _ in range(num_rtt_measurements)])
            rtt_avg = np.mean(rtts)
            print(f"RTT: {rtt_avg:.1f} +/- {np.std(rtts):.1f} ms")

            # get the reference times from the browser and LSL
            # should be the same timing as much as possible
            nonlocal ref_time_browser
            ref_time_lsl = local_clock()  # first get LSL time
            ref_time_browser = await sio.call("getTime", to=sid) - rtt_avg / 2  # then get RTT-corrected browser time

            save_path = Path(__file__).parent / "logs" / username / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.hdf5"
            save_path.parent.mkdir(parents=True, exist_ok=True)  # make devices/eeg/logs/username/

            recorder = Recorder(
                input_observable,
                input_nch,
                save_path=save_path,
                chunk_size=input_freq * record_interval,
                ref_time=ref_time_lsl,
            )
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

    @sio.on("dataCollectionOnset")
    async def data_collection_onset(sid: str, data: dict) -> None:
        for runner in runners:
            if not isinstance(runner, Recorder):
                continue
            cue = data["cue"]
            timestamp = (data["timestamp"] - ref_time_browser) / 1000  # sec
            runner.record_onset(cue, timestamp)
            # trailing space in case of no line break
            print(f"Received data collection onset: '{cue}' at {timestamp:.2f}s ")

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
