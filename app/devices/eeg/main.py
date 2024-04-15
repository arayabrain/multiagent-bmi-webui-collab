from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import click
import socketio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pylsl import resolve_streams

from app.devices.eeg.baseline import measure_baseline
from app.devices.eeg.decoder import Decoder
from app.devices.eeg.models.threshold_model import ThresholdModel as Model
from app.devices.eeg.recorder import Recorder
from app.devices.utils.networking import create_observable_from_stream_inlet, get_ref_time, get_stream_inlet

use_diff = False


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
@click.option(
    "--window-duration",
    "-wdur",
    default=0.1,  # long window can cause delay
    type=click.FloatRange(min=0),
    help="Window duration in seconds",
)
@click.option("--thres", "-t", default=12.0, type=click.FloatRange(min=0), help="Threshold for channel activation")
@click.option("--model-datetime", "-d", default="", type=str, help="Date of the model to load")
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
    window_duration,
    thres,
    model_datetime,
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
        command_labels = data["commandLabels"]
        num_classes = len(command_labels)

        if len(runners) > 0:
            # if the runners are already set up, do nothing
            print("Runners are already set up. Use the existing runners.")
            return

        # Create stream inlets
        while True:
            try:
                stream_infos = resolve_streams(wait_time=1)
                input_inlet = get_stream_inlet(stream_infos, type=input)  # TODO: name
                _info = input_inlet.info()
                input_info: dict = {
                    "name": _info.name(),
                    "type": _info.type(),
                    "channel_count": _info.channel_count(),
                    "nominal_srate": _info.nominal_srate(),
                    "hostname": _info.hostname(),
                    "source_id": _info.source_id(),
                    "session_id": _info.session_id(),
                    "uid": _info.uid(),
                    "command_labels": command_labels,
                }
                print(f"Input stream {input_info['source_id']}: {input_info['nominal_srate']} Hz")
                break
            except LookupError:  # Try again if get_stream_inlet fails
                pass

        # Create observables and set up processing pipeline using Rx
        input_observable = create_observable_from_stream_inlet(input_inlet)

        runners.clear()
        # setup recorder
        if not no_record:
            nonlocal ref_time_browser
            ref_time_lsl, ref_time_browser = await get_ref_time(sio, sid)

            save_path = (
                Path(__file__).parent / "logs" / username / datetime.now().strftime("%Y%m%d_%H%M%S") / "recording.hdf5"
            )
            save_path.parent.mkdir(parents=True, exist_ok=True)  # make devices/eeg/logs/username/

            recorder = Recorder(
                input_observable,
                input_info,
                save_path=save_path,
                record_interval=record_interval,
                ref_time=ref_time_lsl,
            )
            recorder.start()
            runners.append(recorder)

        # measure baseline
        input_freq = input_info["nominal_srate"]
        baseline, baseline_ts = measure_baseline(
            input_observable, baseline_duration, baseline_ready_duration, input_freq, auto_start=auto_baseline
        )
        if not no_record and baseline_ts is not None:
            recorder.record_cue("baseline", baseline_ts[0] - ref_time_lsl)

        # setup decoder
        if not no_decode:
            if not model_datetime:
                model = Model(num_classes, thres, baseline, use_diff=use_diff)
            else:
                print("Ignoring '--thres' because '--model-datetime' is given.")
                model = Model(num_classes, thres, baseline, use_diff=use_diff)  # use thres as a placeholder
                model_path = Path(__file__).parent / "logs" / username / model_datetime / "params.npz"
                model.load(model_path)

            window_size = int(input_freq * window_duration)
            # window_step = window_size // 2
            window_step = None  # no overlap
            decoder = Decoder(input_observable, model, window_size, window_step)
            decoder.set_socket(sio)
            decoder.start()
            runners.append(decoder)

    @sio.on("dataCollectionOnset")
    async def data_collection_onset(sid: str, data: dict) -> None:
        for runner in runners:
            if not isinstance(runner, Recorder):
                continue
            cue = data["cue"]
            timestamp = (data["timestamp"] - ref_time_browser) / 1000  # sec
            runner.record_cue(cue, timestamp)

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
