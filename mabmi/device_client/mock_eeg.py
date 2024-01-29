import time
from threading import Lock, Thread

import numpy as np


class MockEEG:
    def __init__(self, num_channels=128, max_length=5000):
        self.num_channels = num_channels
        self.max_length = max_length
        self.eeg_data = np.zeros((num_channels, 0), dtype=np.float32)
        self.is_running = True
        self.lock = Lock()

    def start(self):
        self.thread = Thread(target=self.generate_eeg, daemon=True)
        self.thread.start()

    def generate_eeg(self):
        while self.is_running:
            length = np.random.randint(1, 11)
            new_eeg = np.random.randn(self.num_channels, length).astype(np.float32)

            with self.lock:
                # データが最大長を超えたら、古いデータを削除
                if self.eeg_data.shape[1] + length > self.max_length:
                    self.eeg_data = self.eeg_data[:, -self.max_length + length :]
                # 新しいデータを末尾に追加
                self.eeg_data = np.concatenate([self.eeg_data, new_eeg], axis=1)

            time.sleep(0.1)

    def pop(self):
        with self.lock:
            data = self.eeg_data
            self.eeg_data = np.zeros((self.num_channels, 0))
        if data.shape[1] == 0:
            return None
        else:
            return data

    def stop(self):
        self.is_running = False
        self.thread.join()


if __name__ == "__main__":
    mock_eeg = MockEEG(max_length=5000)
    mock_eeg.start()

    time.sleep(3)

    eeg_data = mock_eeg.pop()
    print(eeg_data.shape)
    mock_eeg.stop()
