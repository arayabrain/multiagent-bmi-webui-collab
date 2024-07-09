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
        input_info: dict,
        save_path: Path,
        record_interval: float = 5,  # sec
        ref_time: float = 0,  # reference time for timestamps (sec)
    ) -> None:
        self.input_observable = input_observable
        self.subscription: rx.abc.DisposableBase | None = None
        self.is_running = False

        self.input_info = input_info
        self.save_path = save_path
        self.record_interval = record_interval
        self.ref_time = ref_time

    def start(self) -> None:
        if self.is_running:
            print("Recorder is already running.")
            return

        if self.save_path.exists():
            raise RuntimeError("File already exists.")
        self.save_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"Save path: {self.save_path}")

        nch = self.input_info["channel_count"]
        str_dt = h5py.special_dtype(vlen=str)
        with h5py.File(self.save_path, "w") as hf:
            hf.create_dataset("data", (0, nch), maxshape=(None, nch), dtype="f", chunks=True)
            hf.create_dataset("data_ts", (0,), maxshape=(None,), dtype="f", chunks=True)
            hf.create_dataset("cue", (0,), maxshape=(None,), dtype=str_dt, chunks=True)
            hf.create_dataset("cue_ts", (0,), maxshape=(None,), dtype="f", chunks=True)
            # metadata
            for key, value in self.input_info.items():
                if isinstance(value, str):
                    dset = hf.create_dataset(key, (1,), dtype=str_dt)
                    dset[0] = value
                elif isinstance(value, list) and isinstance(value[0], str):
                    dset = hf.create_dataset(key, data=value, dtype=str_dt)
                else:
                    hf.create_dataset(key, data=value)

        chunk_size = int(self.input_info["nominal_srate"] * self.record_interval)
        self.is_running = True
        self.start_time = time.time()

        self.subscription = self.input_observable.pipe(  # type: ignore
            ops.buffer_with_count(chunk_size),
        ).subscribe(
            on_next=self._save,
            on_completed=self.stop,
        )

    def _save(self, buf: list) -> None:
        if not self.is_running:
            return
        recorder_time = time.time() - self.start_time
        data, timestamps = extract_buffer(buf)
        stream_times = timestamps - self.ref_time
        size = len(stream_times)
        with h5py.File(self.save_path, "a") as f:
            f["data"].resize(f["data"].shape[0] + size, axis=0)
            f["data"][-size:] = data
            f["data_ts"].resize(f["data_ts"].shape[0] + size, axis=0)
            f["data_ts"][-size:] = stream_times
        print(
            f"Recorder({recorder_time:.1f}s): recorded {size} samples "
            f"at {stream_times[0]:.1f} - {stream_times[-1]:.1f}s "
        )

    def record_cue(self, cue: str, timestamp: float) -> None:
        """Record the onset of a data collection cue.
        Args:
            cue: Command string of the cue.
            timestamp: Timestamp of the cue (sec).
                Should be the time elapsed from the reference time of the cue source.
        """
        if not self.is_running:
            return
        recorder_time = time.time() - self.start_time
        with h5py.File(self.save_path, "a") as f:
            f["cue"].resize(f["cue"].shape[0] + 1, axis=0)
            f["cue"][-1] = cue
            f["cue_ts"].resize(f["cue_ts"].shape[0] + 1, axis=0)
            f["cue_ts"][-1] = timestamp
        print(f"Recorder({recorder_time:.1f}s): recorded cue '{cue}' at {timestamp:.1f}s ")

    def stop(self) -> None:
        if self.subscription is not None:
            self.subscription.dispose()
        self.is_running = False
        print("Recorder stopped.")
        print(f"Saved recording to: {self.save_path}")
