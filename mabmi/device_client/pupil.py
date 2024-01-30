import asyncio
import json
import threading
import time

import pupil_labs.pupil_core_network_client as pcnc
import websockets
from websockets import WebSocketServerProtocol

debug = False
if debug:
    import logging

    logging.basicConfig(level=logging.DEBUG)


is_running = True
focus: int | None = None
lock = threading.Lock()
connected_clients = set()


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
    prev_focus = None
    _focus = None
    while is_running:
        with lock:
            _focus = focus
        if _focus != prev_focus:
            data = {"type": "gaze", "focusId": _focus}
            await asyncio.wait([client.send(json.dumps(data)) for client in connected_clients])
            prev_focus = _focus
        await asyncio.sleep(0.1)  # TODO


async def ws_handler(websocket: WebSocketServerProtocol, path):
    # register client
    connected_clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        connected_clients.remove(websocket)


async def main():
    address = "127.0.0.1"
    pupil_port = 50020
    ws_port = 8001

    print("Connecting to Pupil Core...")
    pupil = pcnc.Device(address, pupil_port)
    pupil.send_notification({"subject": "frame_publishing.set_format", "format": "bgr"})
    print("Pupil Core Connected.")

    gaze_thread = threading.Thread(target=receive_gaze_and_update_focus, args=(pupil,))
    gaze_thread.start()

    # Start the WebSocket server
    async with websockets.serve(ws_handler, address, ws_port):
        await send_focus()

    gaze_thread.join()


if __name__ == "__main__":
    asyncio.run(main(), debug=debug)
