from pathlib import Path

import numpy as np
from typing import Union, Tuple

from app.devices.utils.utils import root_mean_square


class ThresholdModel:
    def __init__(
        self,
        num_classes: int,
        thres: Union[np.ndarray, None],  # (num_classes,)
        baseline: Union[np.ndarray, None] = None,  # (times, channels)
        use_diff: bool = False,
    ):
        self.num_classes = num_classes
        if thres is not None:
            self.thres = thres
        else:
            self.thres = np.ones(num_classes)
        if baseline is not None:
            self.baseline_rms = root_mean_square(baseline)
        else:
            self.baseline_rms = np.ones(num_classes)

        self.class_output_flags = [False] * num_classes
        self.flag_reset_margin = 0.2

        self.use_diff = use_diff
        if use_diff:
            self.prev_rms_ratio = np.ones(num_classes)

    def __call__(self, data: np.ndarray) -> Tuple[Union[int, None], np.ndarray]:
        rms = root_mean_square(data)  # (channel,)
        rms_ratio = rms / self.baseline_rms
        if not self.use_diff:
            x = rms_ratio  # (channel,)
        else:
            x = np.maximum(0, rms_ratio - self.prev_rms_ratio)  # ignore negative values
            self.prev_rms_ratio = rms_ratio

        # ensure the length is equal to the number of classes
        # TODO: remove?
        if len(x) < self.num_classes:
            # zero-padding at the end
            x = np.pad(x, (0, self.num_classes - len(x)))
        elif len(x) > self.num_classes:
            # truncate
            x = x[: self.num_classes]

        likelihoods = x / self.thres  # element-wise division
        max_ch = int(np.argmax(likelihoods))  # the channel with the highest likelihood
        if likelihoods[max_ch] < 1 or self.class_output_flags[max_ch]:
            # if the max_ch has already been output, do not output the same class again
            out = None
        else:
            out = max_ch
            self.class_output_flags[max_ch] = True

        # reset the output flag if the likelihood is below (1 - margin)
        for i in range(self.num_classes):
            if likelihoods[i] < 1 - self.flag_reset_margin:
                self.class_output_flags[i] = False

        return out, likelihoods

    def fit(self, X, y):
        # X: (epoch, channel, time)
        # y: (epoch,) int
        rms = np.array([root_mean_square(x.T) for x in X])  # (epoch, channel)
        if not self.use_diff:
            X_ = rms / self.baseline_rms  # (epoch, channel)
        else:
            init_rms = self.baseline_rms[np.newaxis, :]
            rms = np.vstack([init_rms, rms])
            rms_diff_ratio = np.diff(rms, axis=0) / self.baseline_rms
            X_ = np.maximum(0, rms_diff_ratio)  # ignore negative values

        self.thres = np.array([np.median(X_[y == i][:, i]) for i in range(self.num_classes)])
        print(f"Thresholds: {self.thres}")
        # for i in range(self.num_classes):
        #     print(X_[y == i][:, i])

        return self

    def save(self, path: Path):
        assert path.suffix == ".npz"
        np.savez(path, thres=self.thres)

    def load(self, path: Path):
        assert path.suffix == ".npz"
        with np.load(path) as f:
            self.thres = f["thres"]
