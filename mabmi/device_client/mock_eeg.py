import time
from threading import Lock, Thread

import numpy as np
from numpy_ringbuffer import RingBuffer


class MockEEG:
    def __init__(self, num_channels=128, max_length=5000, interval=0.1):
        self.num_channels = num_channels
        self.max_length = max_length
        self.interval = interval
        self.eeg_buf = RingBuffer(capacity=max_length, dtype=(np.float32, num_channels))  # (n_samples, n_chs)
        self.ts_buf = RingBuffer(capacity=max_length, dtype=np.float32)  # (n_samples,)
        self.is_running = True
        self.lock = Lock()

    def reset(self):
        with self.lock:
            self.eeg_buf._left_index = 0
            self.eeg_buf._right_index = 0
            self.ts_buf._left_index = 0
            self.ts_buf._right_index = 0

    def start(self):
        self.thread = Thread(target=self.generate_eeg, daemon=True)
        self.thread.start()

    def generate_eeg(self):
        while self.is_running:
            length = np.random.randint(1, 11)
            new_eeg = np.random.randn(length, self.num_channels).astype(np.float32)
            new_ts = np.ones(length) * time.time()

            with self.lock:
                self.eeg_buf.extend(new_eeg)
                self.ts_buf.extend(new_ts)

            time.sleep(self.interval)

    def pop(self):
        with self.lock:
            eeg = self.eeg_buf._unwrap()  # (n_chs, n_samples)
            ts = self.ts_buf._unwrap()  # (n_samples,)
        self.reset()

        return eeg, ts

    def stop(self):
        self.is_running = False
        self.thread.join()


if __name__ == "__main__":
    T = 5
    mock_eeg = MockEEG(max_length=5000)
    mock_eeg.start()

    for _ in range(10):
        print(mock_eeg.eeg_buf.shape)
        time.sleep(T / 10)

    eeg, ts = mock_eeg.pop()
    print(f"pop: eeg {eeg.shape}, timestamps {ts.shape}")

    mock_eeg.stop()
