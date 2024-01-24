import asyncio
import json
import threading
import time

import pupil_labs.pupil_core_network_client as pcnc
import websockets

# import logging
# logging.basicConfig(level=logging.DEBUG)

is_running = True
focus: int | None = None
lock = threading.Lock()


def compute_focus_area(x, y):
    # (0, 0) is the bottom-left corner
    if 0 <= x < 0.5:
        if 0.5 <= y <= 1:
            return 0
        elif 0 <= y < 0.5:
            return 2
    elif 0.5 <= x <= 1:
        if 0.5 <= y <= 1:
            return 1
        elif 0 <= y < 0.5:
            return 3

    return None


def receive_gaze_and_update_focus(pupil):
    global is_running, focus

    with pupil.subscribe_in_background("surface", buffer_size=1) as sub:
        while is_running:
            message = sub.recv_new_message(timeout_ms=1000)
            if message is None:
                continue
            assert message.payload["name"] == "Surface 1"
            x, y = message.payload["gaze_on_surfaces"][-1]["norm_pos"]  # use latest gaze
            # print(f"({x}, {y})")
            new_focus = compute_focus_area(x, y)
            with lock:
                focus = new_focus

            time.sleep(0.1)


async def send_focus():
    global is_running, focus
    uri = "ws://localhost:8000/pupil"
    max_retry = 3
    retry_cnt = 0

    while is_running and max_retry >= 0:
        try:
            async with websockets.connect(uri) as websocket:
                print("Websocket Connected.")
                retry_cnt = 0  # reset retry counter on successful connection
                prev_focus = None
                _focus = None
                while is_running:
                    with lock:
                        _focus = focus
                    if _focus != prev_focus:
                        data = {"type": "gaze", "focusId": _focus}
                        await websocket.send(json.dumps(data))
                        prev_focus = _focus
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
    address = "127.0.0.1"
    port = 50020

    print("Connecting to Pupil Core...")
    pupil = pcnc.Device(address, port)
    pupil.send_notification({"subject": "frame_publishing.set_format", "format": "bgr"})
    print("Pupil Core Connected.")

    gaze_thread = threading.Thread(target=receive_gaze_and_update_focus, args=(pupil,))
    gaze_thread.start()
    await send_focus()
    gaze_thread.join()


if __name__ == "__main__":
    asyncio.run(main(), debug=True)
