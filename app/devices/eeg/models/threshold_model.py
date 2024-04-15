from pathlib import Path

import numpy as np

from app.devices.utils.utils import root_mean_square


class ThresholdModel:
    def __init__(
        self,
        num_classes: int,
        thres: float,
        baseline: np.ndarray | None = None,  # (times, channels)
    ):
        self.num_classes = num_classes
        self.thres = thres
        if baseline is not None:
            self.baseline_rms = root_mean_square(baseline)
        else:
            self.baseline_rms = np.ones(num_classes)

        self.class_output_flags = [False] * num_classes
        self.flag_reset_margin = 0.2

    def __call__(self, data: np.ndarray) -> tuple[int | None, np.ndarray]:
        rms_ratio = root_mean_square(data) / self.baseline_rms

        # ensure the length of rms_ratio is equal to the number of classes
        if len(rms_ratio) < self.num_classes:
            # zero-padding at the end
            rms_ratio = np.pad(rms_ratio, (0, self.num_classes - len(rms_ratio)))
        elif len(rms_ratio) > self.num_classes:
            # truncate
            rms_ratio = rms_ratio[: self.num_classes]

        likelihoods = rms_ratio / self.thres
        max_cls = int(np.argmax(likelihoods))
        if likelihoods[max_cls] < 1 or self.class_output_flags[max_cls]:
            # if the max_cls is already output, do not output the same class again
            cls = None
        else:
            cls = max_cls
            self.class_output_flags[max_cls] = True

        # reset the output flag if the likelihood is below (1 - margin)
        for i in range(self.num_classes):
            if likelihoods[i] < 1 - self.flag_reset_margin:
                self.class_output_flags[i] = False

        return cls, likelihoods

    def fit(self, X, y):
        # X: (epoch, channel, time)
        # y: (epoch,) int
        rms_ratio = [root_mean_square(x.T) / self.baseline_rms for x in X]
        rms_ratio_true = [ratio[y_] for ratio, y_ in zip(rms_ratio, y)]
        self.thres = np.median(rms_ratio_true)
        return self

    def save(self, path: Path):
        assert path.suffix == ".npz"
        np.savez(path, thres=self.thres)

    def load(self, path: Path):
        assert path.suffix == ".npz"
        with np.load(path) as f:
            self.thres = f["thres"]


# TODO: integrate this with ThresholdModel
class ThresholdDiffModel:
    def __init__(
        self,
        num_classes: int,
        thres: float,
        baseline: np.ndarray | None = None,  # (times, channels)
    ):
        self.num_classes = num_classes
        self.thres = thres
        if baseline is not None:
            self.baseline_rms = root_mean_square(baseline)
        else:
            self.baseline_rms = np.ones(num_classes)

        self.prev_rms = self.baseline_rms
        self.class_output_flags = [False] * num_classes
        self.flag_reset_margin = 0.2

    def __call__(self, data: np.ndarray) -> tuple[int | None, np.ndarray]:
        rms = root_mean_square(data)
        rms_ratio_diff = (rms - self.prev_rms) / self.baseline_rms
        self.prev_rms = rms

        # ensure the length of rms_ratio_diff is equal to the number of classes
        if len(rms_ratio_diff) < self.num_classes:
            # zero-padding at the end
            rms_ratio_diff = np.pad(rms_ratio_diff, (0, self.num_classes - len(rms_ratio_diff)))
        elif len(rms_ratio_diff) > self.num_classes:
            # truncate
            rms_ratio_diff = rms_ratio_diff[: self.num_classes]

        likelihoods = np.maximum(rms_ratio_diff, 0) / self.thres  # ignore negative values
        max_cls = int(np.argmax(likelihoods))
        if likelihoods[max_cls] < 1 or self.class_output_flags[max_cls]:
            # if the max_cls is already output, do not output the same class again
            cls = None
        else:
            cls = max_cls
            self.class_output_flags[max_cls] = True

        # reset the output flag if the likelihood is below (1 - margin)
        for i in range(self.num_classes):
            if likelihoods[i] < 1 - self.flag_reset_margin:
                self.class_output_flags[i] = False

        return cls, likelihoods
