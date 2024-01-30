import asyncio
import sys

import msgpack
import zmq.asyncio
from mock_eeg import MockEEG

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

mock = MockEEG(max_length=5000, interval=1)
get_eeg = mock.pop


async def transfer_eeg(socket: zmq.asyncio.Socket):
    global is_running

    while is_running:
        # send eeg data
        eeg, ts = get_eeg()
        if len(ts) == 0:
            await asyncio.sleep(0.05)  # TODO
            continue

        print(f"Sending data {eeg.shape} {ts.shape}")
        eeg_bytes = eeg.tobytes()
        ts_bytes = ts.tobytes()
        metadata = {
            "eeg_dtype": eeg.dtype.str,
            "eeg_shape": eeg.shape,
            "ts_dtype": ts.dtype.str,
            "ts_shape": ts.shape,
        }
        await socket.send(msgpack.packb((metadata, eeg_bytes, ts_bytes)))

    # TODO: error handling


async def main(socket: zmq.asyncio.Socket):
    global is_running

    try:
        await transfer_eeg(socket)
    except KeyboardInterrupt:
        is_running = False


if __name__ == "__main__":
    is_running = True

    context = zmq.asyncio.Context()
    socket = context.socket(zmq.PUB)
    socket.connect("tcp://127.0.0.1:5555")

    mock.start()
    asyncio.run(main(socket))
    mock.stop()
    context.term()
