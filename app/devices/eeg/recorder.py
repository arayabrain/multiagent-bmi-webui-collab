import time
from pathlib import Path

import h5py
import reactivex as rx
from reactivex import operators as ops

from app.devices.utils.networking import extract_buffer


class Recorder:
    def __init__(
        self,
        input_observable: rx.Observable,
        input_nch: int,
        save_path: Path,
        chunk_size: int = 5000,
        ref_time: float = 0,  # reference time for timestamps (sec)
    ) -> None:
        self.input_observable = input_observable
        self.subscription: rx.abc.DisposableBase | None = None
        self.is_running = False

        self.input_nch = input_nch
        self.save_path = save_path
        self.chunk_size = chunk_size
        self.ref_time = ref_time

    def start(self) -> None:
        if self.save_path.exists():
            print(f"Appending to existing file: {self.save_path}")
        else:
            print(f"Creating new file: {self.save_path}")
            self.save_path.parent.mkdir(parents=True, exist_ok=True)
        with h5py.File(self.save_path, "a") as f:
            if "data" not in f:
                f.create_dataset("data", (0, self.input_nch), maxshape=(None, self.input_nch), dtype="f", chunks=True)
            if "timestamp" not in f:
                f.create_dataset("timestamp", (0,), maxshape=(None,), dtype="f", chunks=True)
            if "onset" not in f:
                f.create_dataset("onset", (0,), maxshape=(None,), dtype="f", chunks=True)
            if "cue" not in f:
                dt = h5py.string_dtype(encoding="utf-8")
                f.create_dataset("cue", (0,), maxshape=(None,), dtype=dt, chunks=True)

        self.start_time = time.time()
        self.is_running = True

        self.subscription = self.input_observable.pipe(  # type: ignore
            ops.buffer_with_count(self.chunk_size),
        ).subscribe(
            on_next=self._save,
            on_completed=self.stop,
        )

    def _save(self, buf: list) -> None:
        elapsed_time = time.time() - self.start_time
        data, timestamps = extract_buffer(buf)
        size = len(timestamps)

        with h5py.File(self.save_path, "a") as f:
            f["data"].resize(f["data"].shape[0] + size, axis=0)
            f["data"][-size:] = data
            f["timestamp"].resize(f["timestamp"].shape[0] + size, axis=0)
            f["timestamp"][-size:] = timestamps - self.ref_time

        print(f"{elapsed_time:.1f}s: recorded {size} samples")

    def record_onset(self, cue: str, timestamp: float) -> None:
        """Record the onset of a data collection cue.
        Args:
            cue: The command string of the cue.
            timestamp: The timestamp of the onset (sec).
                Should be relative to the browser reference time.
        """
        with h5py.File(self.save_path, "a") as f:
            size = f["onset"].shape[0]
            f["onset"].resize(size + 1, axis=0)
            f["onset"][-1] = timestamp
            f["cue"].resize(size + 1, axis=0)
            f["cue"][-1] = cue

    def stop(self) -> None:
        if self.subscription is not None:
            self.subscription.dispose()
        self.is_running = False
        print("Recorder stopped.")
        print(f"Save path: {self.save_path}")
