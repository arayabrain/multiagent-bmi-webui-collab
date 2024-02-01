import asyncio
import json
import random
import threading
import time

import websockets
from websockets import WebSocketServerProtocol

debug = False

is_running = True

focus: int | None = None
focus_event = asyncio.Event()
lock = threading.Lock()

connected_clients = set()
connect_event = asyncio.Event()


def compute_focus_area():
    return random.randint(0, 3)


def receive_gaze_and_update_focus(loop):
    global is_running, focus
    while is_running:
        new_focus = compute_focus_area()
        if new_focus != focus:
            print(f"New focus: {new_focus}")
            with lock:
                focus = new_focus
            loop.call_soon_threadsafe(focus_event.set)

        time.sleep(0.1)


async def send_focus():
    global is_running, focus
    prev_focus = None
    _focus = None
    while is_running:
        await connect_event.wait()
        await focus_event.wait()

        with lock:
            _focus = focus
        assert _focus != prev_focus  # focus should be changed

        data = json.dumps({"type": "gaze", "focusId": _focus})
        await asyncio.wait([asyncio.create_task(client.send(data)) for client in connected_clients])
        print(f"Sent focus: {_focus}")

        prev_focus = _focus
        focus_event.clear()


async def handler(websocket: WebSocketServerProtocol):
    print("Client connected")
    if len(connected_clients) == 0:
        connect_event.set()
    connected_clients.add(websocket)

    await websocket.wait_closed()

    print("Client disconnected")
    connected_clients.remove(websocket)
    if len(connected_clients) == 0:
        connect_event.clear()


async def main():
    ws_address = "127.0.0.1"
    ws_port = 8001

    loop = asyncio.get_running_loop()
    gaze_thread = threading.Thread(target=receive_gaze_and_update_focus, args=(loop,))
    gaze_thread.start()

    # Start the WebSocket server
    async with websockets.serve(handler, ws_address, ws_port):
        await send_focus()

    gaze_thread.join()


if __name__ == "__main__":
    asyncio.run(main(), debug=debug)
