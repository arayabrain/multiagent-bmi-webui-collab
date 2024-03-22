import time
from multiprocessing import Process
from pathlib import Path

import mne
import numpy as np
import pandas as pd
import pylsl
from matplotlib import pyplot as plt
from mne.io import constants
from pyxdf import resolve_streams
from tqdm import tqdm

from app.devices.mock_eeg_streamer.mnelab_io import read_raw_xdf


def xdf2raw(
    xdf_path,
    min_n_ch=None,
    need_filter=False,
    start_sec=0,
    plot=False,
    fs_new=None,  # XXX: workaround to avoid mismatch between the info and the data
):
    xdf_path = Path(xdf_path)
    stream_info = resolve_streams(xdf_path)
    df = pd.DataFrame(stream_info)
    eeg_metadata = df[df.type == "EEG"]
    stream_ids = eeg_metadata.stream_id.values
    if fs_new is None:
        fs_new = eeg_metadata.nominal_srate.values[0]
    raw = read_raw_xdf(xdf_path, stream_ids=stream_ids, fs_new=fs_new)

    # overwrite the channel types
    ch_types = ["eeg"] * len(raw.info["ch_names"])
    raw.set_channel_types({ch: ch_type for ch, ch_type in zip(raw.info["ch_names"], ch_types)})

    # preprocessing
    if need_filter:
        raw.filter(1, 40, picks=["misc"])
    if start_sec > 0:
        raw.crop(tmin=start_sec)

    # increase the number of channels to min_n_ch
    n_ch = raw.info["nchan"]
    if min_n_ch is not None and n_ch < min_n_ch:
        offset_samp = int(5 * fs_new)  # shift the data by 5 seconds (* channel index)
        data = raw.get_data()
        new_ch_data_ls = []
        new_ch_name_ls = []
        for i in range(min_n_ch - n_ch):
            ch_data = np.roll(data[i % n_ch, :], (i + 1) * offset_samp)
            new_ch_data_ls.append(ch_data)
            new_ch_name_ls.append(f"dummy_{i}")

        new_info = mne.create_info(new_ch_name_ls, fs_new, ch_types="eeg")
        new_raw = mne.io.RawArray(np.array(new_ch_data_ls), new_info)
        raw.add_channels([new_raw], force_update_info=True)

    if plot:
        T = raw.n_times / raw.info["sfreq"]
        raw.plot(duration=T / 2, scalings={"eeg": 5e2, "misc": 5e2})
        plt.show()

    return raw


class MockLSLStream(object):
    """Mock LSL Stream.

    Parameters
    ----------
    host : str
        The LSL identifier of the server.
    raw : instance of Raw object
        An instance of Raw object to be streamed.
    ch_type : str
        The type of data that is being streamed.
    time_dilation : int
        A scale factor to speed up or slow down the rate of
        the data being streamed.
    status : bool
        If True, give status updates every ``sfreq`` samples.
    """

    def __init__(self, host, raw, lsl_type, time_dilation=1, report_status=False):
        self._host = host
        self._lsl_type = lsl_type
        self._time_dilation = time_dilation

        self._raw = raw
        self._sfreq = int(self._raw.info["sfreq"])
        self._report_status = bool(report_status)

    def start(self):
        """Start a mock LSL stream."""
        if self._report_status:
            print("Now sending data...")
        self._streaming = True
        self.process = Process(target=self._initiate_stream, daemon=True)
        self.process.start()
        return self

    def stop(self):
        """Stop a mock LSL stream."""
        self._streaming = False
        if self._report_status:
            print("Stopping stream...")
        self.process.terminate()
        return self

    def __enter__(self):
        """Enter the context manager."""
        self.start()
        return self

    def __exit__(self, type_, value, traceback):
        """Exit the context manager."""
        self.stop()

    def _initiate_stream(self):
        # outlet needs to be made on the same process
        info = pylsl.StreamInfo(
            name="MNE",
            type=self._lsl_type.upper(),
            channel_count=self._raw.info["nchan"],
            nominal_srate=self._sfreq,
            channel_format="float32",
            source_id=self._host,
        )
        info.desc().append_child_value("manufacturer", "MNE")
        channels = info.desc().append_child("channels")
        for ch in self._raw.info["chs"]:
            unit = ch["unit"]
            keys, values = zip(*list(constants.FIFF.items()))
            unit = keys[values.index(unit)]
            channels.append_child("channel").append_child_value("label", ch["ch_name"]).append_child_value(
                "type", self._lsl_type.lower()
            ).append_child_value("unit", unit)

        # next make an outlet
        outlet = pylsl.StreamOutlet(info)

        # let's make some data
        counter = 0
        delta = self._time_dilation / self._sfreq  # desired push step
        next_t = time.time()
        len_data = self._raw.last_samp - self._raw.first_samp

        pbar = tqdm(
            total=len_data / self._sfreq,
            desc="Sending data",
            unit="s",
            unit_scale=True,
        )
        while self._streaming:
            mysample = self._raw[:, counter][0].ravel()
            # now send it and wait for a bit
            outlet.push_sample(mysample)

            pbar.update(1 / self._sfreq)
            if counter == len_data:
                counter = 0
                pbar.reset()
            else:
                counter += 1

            next_t += delta
            sleep = next_t - time.time()
            if sleep > 0:
                time.sleep(sleep)


if __name__ == "__main__":
    data_path = Path("app/devices/mock_eeg_streamer/data")
    # filename = "emg-marina-20240215.xdf"
    # need_filter = True
    # start_sec = 13
    filename = "emg-marina-20240216-filtered.xdf"
    min_n_ch = 4
    need_filter = False
    start_sec = 0
    # plot = True
    plot = False

    raw = xdf2raw(data_path / filename, min_n_ch=min_n_ch, need_filter=need_filter, start_sec=start_sec, plot=plot)
    with MockLSLStream("MockEMG", raw, "EEG", time_dilation=1, report_status=True) as stream:
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print("Interrupted")
        finally:
            stream.stop()
            print("Done")
