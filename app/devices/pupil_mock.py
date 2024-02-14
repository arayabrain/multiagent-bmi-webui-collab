import asyncio
import json
import random
import threading
import time

import websockets
from websockets import WebSocketServerProtocol

ws_address = "127.0.0.1"
ws_port = 8001

is_running = True

focus: int | None = None
prev_focus: int | None = None
focus_event = asyncio.Event()
lock = threading.Lock()

connected_clients = set()
connect_event = asyncio.Event()


def receive_gaze_and_update_focus(loop):
    global is_running, focus
    while is_running:
        new_focus = random.randint(0, 3)
        if new_focus != focus:
            # print(f"New focus: {new_focus}")
            with lock:
                focus = new_focus
            loop.call_soon_threadsafe(focus_event.set)

        # time.sleep(0.1)
        time.sleep(1)


async def send_focus():
    global is_running, focus, prev_focus
    _focus = None

    try:
        while is_running:
            await connect_event.wait()
            await focus_event.wait()

            with lock:
                _focus = focus
            assert _focus != prev_focus  # focus should be changed

            data = json.dumps({"type": "gaze", "focusId": _focus})
            if not connected_clients:  # sometimes client disconnects while waiting for focus
                continue
            await asyncio.wait([asyncio.create_task(client.send(data)) for client in connected_clients])
            print(f"Sent focus {_focus}")

            prev_focus = _focus
            focus_event.clear()
    except asyncio.CancelledError:
        # task.cancel() is called
        return


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

        global prev_focus
        prev_focus = None  # reset prev_focus


async def run_server():
    async with websockets.serve(handler, ws_address, ws_port):
        await send_focus()


def main():
    loop = asyncio.get_event_loop()
    task = loop.create_task(run_server())
    gaze_thread = threading.Thread(target=receive_gaze_and_update_focus, args=(loop,))
    gaze_thread.start()
    print("Gaze thread started.")

    try:
        loop.run_until_complete(task)
    except KeyboardInterrupt:
        print("KeyboardInterrupt. Exiting...")
        task.cancel()
        loop.run_until_complete(task)  # wait until task is cancelled
    finally:
        global is_running
        is_running = False
        if gaze_thread.is_alive():
            gaze_thread.join()
        loop.close()


if __name__ == "__main__":
    main()
