import asyncio
import json
import logging
import threading

import pupil_labs.pupil_core_network_client as pcnc
import websockets

logging.basicConfig(level=logging.DEBUG)

is_running = True
focus = None
lock = threading.Lock()


def compute_focus_area(x, y):
    if 0 <= x < 0.5:
        if 0 <= y < 0.5:
            return 0
        elif 0.5 <= y < 1:
            return 2
    elif 0.5 <= x < 1:
        if 0 <= y < 0.5:
            return 1
        elif 0.5 <= y < 1:
            return 3

    return None


def receive_gaze_and_update_focus(pupil):
    global is_running, focus

    with pupil.subscribe_in_background("fixation", buffer_size=1) as sub:
        while is_running:
            message = sub.recv_new_message(timeout_ms=1000)
            if message is None:
                continue
            x, y = message.payload["norm_pos"]
            new_focus = compute_focus_area(x, y)
            print(f"({x:.2f}, {y:2f}): {new_focus}", flush=True)
            if new_focus is not None:
                with lock:
                    focus = new_focus


async def send_focus():
    print("000", flush=True)
    global is_running, focus
    uri = "ws://localhost:8000/ws/input"

    async with websockets.connect(uri) as websocket:
        try:
            prev_focus = None
            _focus = None
            while is_running:
                with lock:
                    _focus = focus
                if _focus != prev_focus:
                    data = {"type": "gaze", "focus_id": _focus}
                    await websocket.send(json.dumps(data))
                    prev_focus = _focus
                await asyncio.sleep(0.1)  # TODO
        except websockets.exceptions.ConnectionClosedError:
            print("Connection closed.")
            is_running = False


async def main():
    address = "127.0.0.1"
    port = 50020

    print("Connecting to Pupil Core...")
    pupil = pcnc.Device(address, port)
    pupil.send_notification({"subject": "frame_publishing.set_format", "format": "bgr"})
    print("Connected.")

    gaze_thread = threading.Thread(target=receive_gaze_and_update_focus, args=(pupil,))
    gaze_thread.start()
    await send_focus()
    gaze_thread.join()


if __name__ == "__main__":
    asyncio.run(main(), debug=True)
