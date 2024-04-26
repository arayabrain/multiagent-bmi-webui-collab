from pathlib import Path

import click
import h5py
import mne
import numpy as np

from app.devices.eeg.models.threshold_model import ThresholdModel as Model
from app.devices.utils.database import DatabaseManager


def load_data(hdf_path, window_duration, baseline_duration):
    with h5py.File(hdf_path, "r") as hf:
        data = hf["data"][:]  # (time, channel) float
        # data_ts = hf["data_ts"][:]  # (time,) float
        cue = hf["cue"][:]  # (time,) bytes
        cue_ts = hf["cue_ts"][:]  # (time,) float
        command_labels = hf["command_labels"][:]  # (num_classes,) str
        sfreq = hf["nominal_srate"][()]
        nch = hf["channel_count"][()]
    cue = np.array([cue.decode("utf-8") for cue in cue])
    command_labels = np.array([label.decode("utf-8") for label in command_labels])

    # create MNE Raw object
    ch_names = [f"ch{i}" for i in range(nch)]  # TODO: can get this from stream info?
    info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types="eeg")
    raw = mne.io.RawArray(data.T, info=info)

    # annotation
    durations = [baseline_duration if cue == "baseline" else 0 for cue in cue]
    annot = mne.Annotations(onset=cue_ts, duration=durations, description=cue)
    raw.set_annotations(annot)

    # crop raw into 5s before and after cue
    raw.crop(tmin=max(0, cue_ts[0] - 5), tmax=min(cue_ts[-1] + 5, raw.times[-1]))

    # plot for debugging
    fig = raw.plot(start=0, duration=100, scalings={"eeg": 1e3})
    fig.savefig(hdf_path.parent / "raw.png")

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

    return X, y, baseline, command_labels


def train(X, y, labels, baseline, save_path):
    model = Model(len(labels), None, baseline.T)
    model.fit(X, y)
    model.save(save_path)


@click.command()
@click.option("--user-id", "-u", help="User ID for the data collection recording to train on.")
@click.option("--exp-id", "-d", help="Experiment ID for the data collection recording to train on.")
@click.option(
    "--load-latest-recording",
    is_flag=True,
    help="Use the latest recording data for training instead of manually specifying user_id and exp_id",
)
@click.option("--window-duration", "-wdur", default=2.0, help="Duration of window per cue in seconds.")
@click.option("--baseline-duration", "-bdur", default=5.0, help="Duration of the baseline in seconds.")
def main(user_id, exp_id, load_latest_recording, window_duration, baseline_duration):
    save_root = Path(__file__).parent / "logs"
    db_manager = DatabaseManager(save_root / "data.yaml")

    if load_latest_recording:
        user_id, exp_id = db_manager.get_latest_recording_info(user_id)
    elif user_id is None or exp_id is None:
        raise ValueError("Specify user_id and exp_id or use --load-latest-recording")
    print(f"Training for user {user_id} and experiment {exp_id}")
    log_dir = Path(__file__).parent / "logs" / user_id / exp_id

    hdf_path = log_dir / "recording.hdf5"
    X, y, baseline, labels = load_data(hdf_path, window_duration, baseline_duration)

    model_save_path = log_dir / "params.npz"
    train(X, y, labels, baseline, model_save_path)

    # update the latest model info
    db_manager.update_model_info(user_id, model_save_path)


if __name__ == "__main__":
    main()
