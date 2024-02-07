"""
- Receives EEG data from LSL Stream
- Decodes EEG data
- Sends decoding result to the server via ZMQ
"""

import threading
import time

import click
import numpy as np
import zmq
from pylsl import resolve_streams
from reactivex import operators as ops

from app.utils.networking import create_observable_from_stream_inlet, get_stream_inlet

window_duration = 2  # seconds
baseline_duration = 2  # seconds
baseline_ready_duration = 1  # seconds
thres = 1  # TODO


def rms(data: np.ndarray) -> np.ndarray:
    """Root mean square of each channel in the data.
    Args:
        data: (time, channels)
    Returns:
        rms: (channels,)
    """
    return np.sqrt(np.mean(np.square(data), axis=0))


def get_model():
    def model(
        data: np.ndarray,  # (time, channels)
        baselines: dict,
    ) -> int:
        norm_data = (data - baselines["average"]) / baselines["rms"]
        r = rms(norm_data)
        print(r)
        max_ch = int(np.argmax(r))
        if r[max_ch] > thres:
            return max_ch + 1  # 1-indexed channel number
        else:
            return 0  # stop command

    return model


class Decoder:
    def __init__(self, model, input_observable, window_size, window_step, socket):
        self.model = model
        self.input_observable = input_observable
        self.window_size = window_size
        self.window_step = window_step
        self.socket = socket
        self.subscription = None
        self.baseline_subscription = None
        self.baselines = None
        self.baseline_ready = threading.Event()
        self.is_running = False

    def start(self):
        self.subscription = self.input_observable.pipe(
            ops.buffer_with_count(self.window_size, self.window_step),  # list of (time, channels)
            ops.map(lambda data: np.stack(data).astype(float)),  # (time, channels)  # TODO: float32 or 64?
            ops.map(self._decode),
        ).subscribe(
            on_next=self._publish,
            on_completed=self._on_completed,
        )
        self.is_running = True

    def _decode(self, data: np.ndarray):
        assert self.baselines is not None, "Baseline not set."
        return self.model(data, self.baselines)

    def _publish(self, command: int):
        self.socket.send(command.to_bytes(1, "big"))
        print(f"Sent EEG command: {command}")

    def _on_completed(self):
        print("Decoder completed.")
        self.is_running = False

    def measure_baseline(self, baseline_duration, baseline_ready_duration, input_freq):
        self.baseline_ready.clear()

        # prompt user to keep still
        click.confirm(
            f"\nPreparing to measure the baseline. Press the Enter key, then relax and stay still."
            f"\nMeasurement will start in {baseline_ready_duration}s and will continue for {baseline_duration}s.",
            default=True,
        )

        print(f"Starting baseline measurement in {baseline_ready_duration}s...")
        time.sleep(baseline_ready_duration)

        print("Measuring baseline...")
        self.baseline_subscription = self.input_observable.pipe(
            ops.buffer_with_count(int(baseline_duration * input_freq)),
            ops.take(1),  # take only the first buffer
            ops.map(lambda data: np.stack(data).astype(float)),  # (time, channels)
        ).subscribe(
            on_next=self._set_baseline,
            on_completed=lambda: print("Baseline measurement completed."),
        )

        self.baseline_ready.wait()
        self.baseline_subscription.dispose()

        print(f"Average: {self.baselines['average']}")
        print(f"Root mean square: {self.baselines['rms']}\n")

    def _set_baseline(self, data: np.ndarray):
        self.baselines = {
            "average": np.mean(data, axis=0),
            "rms": rms(data),
        }
        self.baseline_ready.set()

    def stop(self):
        if self.subscription and self.is_running:
            self.subscription.dispose()
            self.is_running = False


class Recorder:
    def __init__(self, input_observable, record_size, save_path="tmp/data.npy"):
        self.input_observable = input_observable
        self.record_size = record_size
        self.save_path = save_path
        self.subscription = None
        self.is_running = False

    def start(self):
        self.subscription = self.input_observable.pipe(
            ops.buffer_with_count(self.record_size),
            ops.take(1),
        ).subscribe(
            on_next=self._save,
            on_completed=self._on_completed,
        )
        self.is_running = True

    def _save(self, buf: list):
        data = np.stack(buf).astype(float)  # (time, channels)
        print(f"Saving data: {data.shape}")
        np.save(self.save_path, data)
        print(f"Recorded data saved to {self.save_path}")

    def _on_completed(self):
        print("Recording completed.")
        self.is_running = False

    def stop(self):
        if self.subscription and self.is_running:
            self.subscription.dispose()
            self.is_running = False


@click.command()
@click.option("--input", default="EEG", type=click.Choice(["EEG", "Audio"]), help="Input type")
@click.option("--mode", default="decode", type=click.Choice(["decode", "record"]), help="Decode or record EEG data")
@click.option(
    "--record-duration", default=5.0, type=click.FloatRange(min=0), help="Duration to record EEG data in seconds"
)
def main(input: str, mode: str, record_duration: float):
    context = zmq.Context()
    socket = context.socket(zmq.PUB)
    socket.connect("tcp://127.0.0.1:5555")

    # Create stream inlets
    while True:
        try:
            stream_infos = resolve_streams(wait_time=1)
            input_inlet = get_stream_inlet(stream_infos, type=input)  # TODO: name
            input_freq = round(input_inlet.info().nominal_srate())
            print(f"Input stream {input_inlet.info().name()}: {input_freq} Hz")
            break
        except LookupError:  # Try again if get_stream_inlet fails
            pass

    # Create observables and set up processing pipeline using Rx
    input_observable = create_observable_from_stream_inlet(input_inlet)

    if mode == "decode":
        model = get_model()
        window_size = input_freq * window_duration
        window_step = window_size // 2
        runner = Decoder(model, input_observable, window_size, window_step, socket)
        runner.measure_baseline(baseline_duration, baseline_ready_duration, input_freq)
    elif mode == "record":
        record_size = input_freq * record_duration
        runner = Recorder(input_observable, record_size)

    runner.start()
    try:
        print("Decoder running... Press Ctrl+C to exit.")
        while runner.is_running:  # Keep main thread alive
            time.sleep(1)
    except KeyboardInterrupt:
        print("KeyboardInterrupt. Exiting...")
        runner.stop()
    finally:
        socket.close()
        context.term()


if __name__ == "__main__":
    main()
