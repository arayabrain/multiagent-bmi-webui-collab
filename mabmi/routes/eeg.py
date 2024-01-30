import msgpack
import numpy as np
from zmq.asyncio import Socket


async def eeg_listener(socket: Socket):
    while not socket.closed:
        metadata, eeg, ts = msgpack.unpackb(await socket.recv(), raw=False)
        eeg = np.frombuffer(eeg, dtype=metadata["eeg_dtype"]).reshape(metadata["eeg_shape"])
        ts = np.frombuffer(ts, dtype=metadata["ts_dtype"]).reshape(metadata["ts_shape"])

        print(f"Received eeg {eeg.shape} {ts.shape}")
