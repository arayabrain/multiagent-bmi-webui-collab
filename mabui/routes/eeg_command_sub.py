import asyncio

from zmq.asyncio import Socket


async def eeg_command_sub(socket: Socket, update_command):
    while not socket.closed:
        try:
            command_byte = await socket.recv()
        except asyncio.CancelledError:
            break
        assert isinstance(command_byte, bytes)
        command = int.from_bytes(command_byte, "big")
        print(f"Received EEG command: {command}")
        update_command({"type": "eeg", "command": command})
