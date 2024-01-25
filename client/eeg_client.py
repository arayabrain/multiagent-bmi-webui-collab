import asyncio
import json
import random
import threading
import time

import websockets

debug = False
if debug:
    import logging

    logging.basicConfig(level=logging.DEBUG)


is_running = True
command: int = 0
lock = threading.Lock()


def receive_eeg_and_update_command():
    global is_running, command

    while is_running:
        # receive eeg data

        # decode and compute command
        # TODO: サーバー側でやる
        _command = random.randint(0, 3)

        # update command
        with lock:
            command = _command

        time.sleep(5)


async def send_command():
    global is_running, command
    uri = "ws://localhost:8000/eeg"
    max_retry = 3
    retry_cnt = 0

    while is_running and max_retry >= 0:
        try:
            async with websockets.connect(uri) as websocket:
                print("Websocket Connected.")
                retry_cnt = 0  # reset retry counter on successful connection
                while is_running:
                    with lock:
                        _command = command
                    data = {"type": "eeg", "command": _command}
                    await websocket.send(json.dumps(data))
                    await asyncio.sleep(0.1)
        except websockets.exceptions.ConnectionClosedError:
            if retry_cnt < max_retry:
                print("Connection closed. Reconnecting in 3 seconds...")
                await asyncio.sleep(3)
                retry_cnt += 1
            else:
                print("Maximum number of retries reached. Exiting...")
                is_running = False
        except ConnectionRefusedError:
            print("Connection refused. Exiting...")
            is_running = False


async def main():
    eeg_thread = threading.Thread(target=receive_eeg_and_update_command)
    eeg_thread.start()
    await send_command()
    eeg_thread.join()


if __name__ == "__main__":
    asyncio.run(main(), debug=debug)
