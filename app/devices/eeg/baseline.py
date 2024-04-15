import threading
import time

import click
import numpy as np
import reactivex as rx
from reactivex import operators as ops

from app.devices.utils.networking import extract_buffer


def measure_baseline(
    input_observable: rx.Observable,
    baseline_duration: float,
    baseline_ready_duration: float,
    input_freq: int,
    auto_start: bool = False,
) -> tuple[np.ndarray, np.ndarray] | tuple[None, None]:
    """Measure the baseline of the signal from the input observable."""
    baseline: np.ndarray | None = None
    timestamp: np.ndarray | None = None
    baseline_ready = threading.Event()

    def set_baseline(buf):
        nonlocal baseline, timestamp
        baseline, timestamp = extract_buffer(buf)
        baseline_ready.set()

    # prompt user to keep still
    confirm = auto_start or click.confirm(
        f"\nPreparing to measure the baseline. Press Enter, then relax and stay still."
        f"\nMeasurement will start in {baseline_ready_duration}s and will continue for {baseline_duration}s.",
        default=True,
    )
    if not confirm:
        print("Baseline measurement cancelled.")
        return None, None

    print(f"Starting baseline measurement in {baseline_ready_duration}s...")
    time.sleep(baseline_ready_duration)

    print("Measuring baseline...")
    baseline_subscription = input_observable.pipe(  # type: ignore
        ops.buffer_with_count(int(baseline_duration * input_freq)),
        ops.take(1),  # take only the first buffer
    ).subscribe(
        on_next=set_baseline,
        on_completed=lambda: print("Baseline measurement completed.\n"),
    )
    baseline_ready.wait()
    baseline_subscription.dispose()

    return baseline, timestamp
