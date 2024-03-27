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
        save_path: str,
        chunk_size=5000,
    ) -> None:
        self.input_observable = input_observable
        self.subscription: rx.abc.DisposableBase | None = None
        self.is_running = False

        self.input_nch = input_nch
        self.chunk_size = chunk_size

        if Path(save_path).is_absolute():
            self.save_path = Path(save_path)
        else:
            self.save_path = Path(__file__).parents[2] / save_path  # relative to the workspace root

    def start(self) -> None:
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

        self.subscription = self.input_observable.pipe(  # type: ignore
            ops.buffer_with_count(self.chunk_size),
        ).subscribe(
            on_next=self._save,
            on_completed=self.stop,
        )

    def _save(self, buf: list) -> None:
        elapsed_time = time.time() - self.start_time
        data, timestamps = extract_buffer(buf)
        size = data.shape[0]

        with h5py.File(self.save_path, "a") as f:
            f["data"].resize(f["data"].shape[0] + size, axis=0)
            f["data"][-size:] = data
            f["timestamps"].resize(f["timestamps"].shape[0] + size, axis=0)
            f["timestamps"][-size:] = timestamps

        print(f"{elapsed_time:.1f}s: recorded {size} samples")

    def stop(self) -> None:
        if self.subscription is not None:
            self.subscription.dispose()
        self.is_running = False
        print("Recorder stopped.")
        print(f"Save path: {self.save_path}")
