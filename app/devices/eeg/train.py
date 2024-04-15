from pathlib import Path

import click
import h5py
import mne
import numpy as np

from app.devices.eeg.models.threshold_model import ThresholdModel as Model


@click.command()
@click.option("--username", "-u", default="testuser", help="Username for the session.")
@click.option("--date", "-d", default="20240412_044751", help="Date for the session.")
@click.option("--window_duration", "-wdur", default=0.1, help="Duration of the window in seconds.")
@click.option("--baseline_duration", "-bdur", default=1.0, help="Duration of the baseline in seconds.")
def main(username, date, window_duration, baseline_duration):
    log_dir = Path(__file__).parent / "logs" / username / date
    save_path = log_dir / "recording.hdf5"
    with h5py.File(save_path, "r") as hf:
        data = hf["data"][:]  # (time, channel) float
        # data_ts = hf["data_ts"][:]  # (time,) float
        cue = hf["cue"][:]  # (time,) bytes
        cue_ts = hf["cue_ts"][:]  # (time,) float
        command_labels = hf["command_labels"][:]  # (num_classes,) str
        sfreq = hf["nominal_srate"][()]
        nch = hf["channel_count"][()]
    cue = np.array([cue.decode("utf-8") for cue in cue])
    command_labels = np.array([command_label.decode("utf-8") for command_label in command_labels])

    # create MNE Raw object
    ch_names = [f"ch{i}" for i in range(nch)]  # TODO: can get this from stream info?
    info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types="eeg")
    raw = mne.io.RawArray(data.T, info=info)

    # annotation
    durations = [baseline_duration if cue == "baseline" else 0 for cue in cue]
    annot = mne.Annotations(
        onset=cue_ts,
        duration=durations,
        description=cue,
    )
    raw.set_annotations(annot)

    # crop raw into 5s before and after cue
    raw.crop(tmin=max(0, cue_ts[0] - 5), tmax=min(cue_ts[-1] + 5, raw.times[-1]))

    # plot for debugging
    fig = raw.plot(start=0, duration=100, scalings={"eeg": 1e3})
    fig.savefig(log_dir / "raw.png")

    # create training data
    event_id = {label: i for i, label in enumerate(command_labels)}
    events, event_id = mne.events_from_annotations(raw, event_id=event_id)
    epochs = mne.Epochs(
        raw, events=events, event_id=event_id, tmin=0, tmax=window_duration, baseline=None, preload=True
    )
    X = epochs.get_data(copy=False)  # (epoch, channel, time)
    y = epochs.events[:, 2]  # (epoch,)

    # baseline
    event_id = {"baseline": 100}
    events, event_id = mne.events_from_annotations(raw, event_id=event_id)
    baseline = mne.Epochs(  # (channel, times)
        raw, events=events, event_id=event_id, tmin=0, tmax=baseline_duration, baseline=None, preload=True
    ).get_data(copy=False)[0]

    model = Model(len(command_labels), 1, baseline.T)
    model.fit(X, y)
    model_path = log_dir / "params.npz"
    model.save(model_path)


if __name__ == "__main__":
    main()
