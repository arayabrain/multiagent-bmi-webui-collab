import numpy as np


def array2str(arr, digits=2):
    return ", ".join([f"{x:.{digits}f}" for x in arr])


def root_mean_square(data: np.ndarray) -> np.ndarray:
    """Root mean square of each channel in the data.
    Args:
        data: np.ndarray, shape (time, channels)
    Returns:
        rms: np.ndarray, shape (channels,)
    """
    return np.sqrt(np.mean(np.square(data), axis=0))
