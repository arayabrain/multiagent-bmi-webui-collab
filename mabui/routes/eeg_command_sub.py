import asyncio
import sys

from zmq.asyncio import Socket


async def eeg_command_sub(socket: Socket, update_command):
    if sys.platform == "win32":
        # deal with a zmq warning on Windows
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    current_policy = asyncio.get_event_loop_policy()
    print(f"Current Event Loop Policy: {current_policy}")

    while not socket.closed:
        command_byte = await socket.recv()
        command = int.from_bytes(command_byte, "big")
        print(f"Received EEG command: {command}")
        update_command({"type": "eeg", "command": command})
