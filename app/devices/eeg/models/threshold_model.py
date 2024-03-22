import numpy as np

from app.devices.eeg.utils import root_mean_square


class ThresholdModel:
    def __init__(self, num_classes: int, thres: float, baselines: dict):
        self.num_classes = num_classes
        self.thres = thres
        self.baselines = baselines

    def __call__(self, data: np.ndarray) -> tuple[int | None, np.ndarray]:
        norm_data = (data - self.baselines["average"]) / self.baselines["rms"]
        rms = root_mean_square(norm_data)

        if len(rms) < self.num_classes:
            # zero-padding at the end
            rms = np.pad(rms, (0, self.num_classes - len(rms)))
        elif len(rms) > self.num_classes:
            # truncate
            rms = rms[: self.num_classes]

        max_ch = int(np.argmax(rms))
        if rms[max_ch] > self.thres:
            cls = max_ch  # output the channel index as class
        else:
            cls = None  # no output class

        return cls, rms  # rms as likelihoods
