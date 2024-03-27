import numpy as np

from app.devices.utils.utils import root_mean_square


class ThresholdModel:
    def __init__(self, num_classes: int, thres: float, baselines: dict):
        self.num_classes = num_classes
        self.thres = thres
        self.baseline_rms = baselines["rms"]

    def __call__(self, data: np.ndarray) -> tuple[int | None, np.ndarray]:
        rms = root_mean_square(data)
        rms_ratio = rms / self.baseline_rms

        if len(rms_ratio) < self.num_classes:
            # zero-padding at the end
            rms_ratio = np.pad(rms_ratio, (0, self.num_classes - len(rms_ratio)))
        elif len(rms_ratio) > self.num_classes:
            # truncate
            rms_ratio = rms_ratio[: self.num_classes]

        max_ch = int(np.argmax(rms_ratio))
        if rms_ratio[max_ch] > self.thres:
            cls = max_ch  # output the channel index as class
        else:
            cls = None  # no output class

        return cls, rms_ratio  # rms ratio as likelihoods


class ThresholdDiffModel:
    def __init__(self, num_classes: int, thres: float, baselines: dict):
        self.num_classes = num_classes
        self.thres = thres
        self.baseline_rms = baselines["rms"]
        self.prev_rms = baselines["rms"]

    def __call__(self, data: np.ndarray) -> tuple[int | None, np.ndarray]:
        rms = root_mean_square(data)
        rms_ratio_diff = (rms - self.prev_rms) / self.baseline_rms
        self.prev_rms = rms

        if len(rms_ratio_diff) < self.num_classes:
            # zero-padding at the end
            rms_ratio_diff = np.pad(rms_ratio_diff, (0, self.num_classes - len(rms_ratio_diff)))
        elif len(rms_ratio_diff) > self.num_classes:
            # truncate
            rms_ratio_diff = rms_ratio_diff[: self.num_classes]

        max_ch = int(np.argmax(rms_ratio_diff))
        if rms_ratio_diff[max_ch] > self.thres:
            cls = max_ch  # output the channel index as class
        else:
            cls = None  # no output class

        likelihoods = np.maximum(rms_ratio_diff, 0)  # ignore negative values
        return cls, likelihoods
