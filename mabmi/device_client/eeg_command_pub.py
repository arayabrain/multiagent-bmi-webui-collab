import asyncio
import random
import sys

import zmq.asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def eeg_command_pub(socket: zmq.asyncio.Socket):
    global is_running

    while is_running:
        # receive EEG
        # decode EEG
        # send result
        command = random.randint(0, 3)
        await socket.send(command.to_bytes(1, "big"))
        print(f"Sent command {command}")

        await asyncio.sleep(1)

    # TODO: error handling


async def main(socket: zmq.asyncio.Socket):
    global is_running

    try:
        await eeg_command_pub(socket)
    except KeyboardInterrupt:
        is_running = False


if __name__ == "__main__":
    is_running = True

    context = zmq.asyncio.Context()
    socket = context.socket(zmq.PUB)
    socket.connect("tcp://127.0.0.1:5555")

    asyncio.run(main(socket))
    context.term()
