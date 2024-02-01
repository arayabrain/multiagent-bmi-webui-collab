import asyncio
import random

import zmq.asyncio

is_running = True


async def eeg_command_pub(socket: zmq.asyncio.Socket):
    while is_running:
        # receive EEG
        # decode EEG
        # send result
        command = random.randint(0, 3)
        await socket.send(command.to_bytes(1, "big"))
        print(f"Sent command {command}")

        await asyncio.sleep(1)


def main():
    context = zmq.asyncio.Context()
    socket = context.socket(zmq.PUB)
    socket.connect("tcp://127.0.0.1:5555")

    try:
        asyncio.run(eeg_command_pub(socket))
    except KeyboardInterrupt:
        print("KeyboardInterrupt. Exiting...")
    finally:
        global is_running
        is_running = False
        socket.close()
        context.term()


if __name__ == "__main__":
    main()
