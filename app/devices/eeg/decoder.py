import asyncio

import numpy as np
import reactivex as rx
import socketio
from reactivex import operators as ops
from typing import Union, Tuple

from app.devices.utils.networking import extract_buffer
from app.devices.utils.utils import array2str

class Decoder:
    """Decode the EEG signal using a model."""

    def __init__(
        self,
        input_observable: rx.Observable,
        model,
        window_size: int,
        window_step: Union[int, None] = None,
    ) -> None:
        self.input_observable = input_observable
        self.subscription = None
        self.is_running = False

        self.model = model
        self.window_size = window_size
        self.window_step = window_step
        self.loop = asyncio.get_event_loop()
        self.sio: socketio.AsyncServer | None = None

    def set_socket(self, sio: socketio.AsyncServer) -> None:
        self.sio = sio

    def start(self) -> None:
        if self.is_running:
            print("Decoder is already running.")
            return

        self.subscription = self.input_observable.pipe(  # type: ignore
            ops.buffer_with_count(self.window_size, self.window_step),  # list of (time, channels)
            ops.map(lambda buf: extract_buffer(buf)[0]),  # type: ignore  # (time, channels)
            ops.map(self._decode),
        ).subscribe(
            on_next=self._publish,
            on_completed=self.stop,
        )
        self.is_running = True

    def _decode(self, data: np.ndarray) -> Tuple[Union[int, None], np.ndarray]:
        return self.model(data)

    def _publish(self, data: Tuple[Union[int, None], np.ndarray]) -> None:
        if self.loop.is_closed():
            return

        class_id, likelihoods = data
        self.loop.create_task(self._emit(class_id, likelihoods))

        class_str = f"{class_id:>4}" if class_id is not None else "None"
        likelihoods_str = array2str(likelihoods)
        print(f"EEG class: {class_str}, likelihoods: {likelihoods_str} ")  # trailing space in case of no line break

    async def _emit(self, cls: Union[int, None], likelihoods: np.ndarray) -> None:
            assert isinstance(self.sio, socketio.AsyncServer), "Socket is not set."
            await self.sio.emit("eeg", {"classId": class_id, "likelihoods": likelihoods.tolist()})

    def stop(self) -> None:
        if self.subscription is not None:
            self.subscription.dispose()
        self.is_running = False
        print("Decoder stopped.")

def measure_baseline(
    input_observable: rx.Observable,
    baseline_duration: float,
    baseline_ready_duration: float,
    input_freq: int,
    auto_start: bool = False,
) -> dict[str, np.ndarray | float]:
    """Measure the baseline of the signal from the input observable."""

    baselines: dict[str, np.ndarray | float] = {"average": 0, "rms": 1}
    baseline_ready = threading.Event()

    def set_baseline(data: np.ndarray):
        baselines["average"] = np.mean(data, axis=0)  # (channels,)
        baselines["rms"] = root_mean_square(data)  # (channels,)
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
        return baselines

    print(f"Starting baseline measurement in {baseline_ready_duration}s...")
    time.sleep(baseline_ready_duration)

    print("Measuring baseline...")
    baseline_subscription = input_observable.pipe(  # type: ignore
        ops.buffer_with_count(int(baseline_duration * input_freq)),
        ops.take(1),  # take only the first buffer
        ops.map(lambda buf: extract_buffer(buf)[0]),  # type: ignore  # (time, channels)
    ).subscribe(
        on_next=set_baseline,
        on_completed=lambda: print("Baseline measurement completed.\n"),
    )
    baseline_ready.wait()
    baseline_subscription.dispose()

    return baselines
