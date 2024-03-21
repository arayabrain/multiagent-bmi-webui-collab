import numpy as np


def root_mean_square(data: np.ndarray) -> np.ndarray:
    """Root mean square of each channel in the data.
    Args:
        data: np.ndarray, shape (time, channels)
    Returns:
        rms: np.ndarray, shape (channels,)
    """
    return np.sqrt(np.mean(np.square(data), axis=0))


def extract_buffer(buf: list) -> tuple:
    """Extract data and timestamps from the buffer.
    Args:
        buf: list of tuple (data, timestamp)
            data: list of float, shape (channels,)
            timestamp: float
    Returns:
        data: np.ndarray, shape (time, channels)  # time = len(buf)
        timestamps: list of float, shape (time,)
    """
    data, timestamps = zip(*buf)
    data = np.array(data, dtype=float)  # TODO: float32 or 64?
    return data, timestamps
