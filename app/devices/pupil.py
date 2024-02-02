import asyncio
import json
import threading
import time

import pupil_labs.pupil_core_network_client as pcnc
import websockets
from websockets import WebSocketServerProtocol

pupil_address = "127.0.0.1"
pupil_port = 50020
ws_address = "127.0.0.1"
ws_port = 8001

is_running = True

focus: int | None = None
focus_event = asyncio.Event()
lock = threading.Lock()

connected_clients = set()
connect_event = asyncio.Event()


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


def receive_gaze_and_update_focus(pupil, loop):
    global is_running, focus

    with pupil.subscribe_in_background("surface", buffer_size=1) as sub:
        while is_running:
            message = sub.recv_new_message(timeout_ms=1000)
            if message is None:
                continue
            assert message.payload["name"] == "Surface 1"  # default name
            gaze = message.payload["gaze_on_surfaces"]
            if not gaze:
                continue
            x, y = gaze[-1]["norm_pos"]  # use only the latest gaze
            # print(f"({x}, {y})")
            new_focus = compute_focus_area(x, y)
            if new_focus != focus:
                # print(f"New focus: {new_focus}")
                with lock:
                    focus = new_focus
                loop.call_soon_threadsafe(focus_event.set)

            time.sleep(0.1)


async def send_focus():
    global is_running, focus
    prev_focus: int | None = -1  # set to -1 instead of None to force sending focus at the beginning
    _focus: int | None = None

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


async def run_server():
    async with websockets.serve(handler, ws_address, ws_port):
        await send_focus()


def connect_to_pupil(address: str, port: int):
    print("Connecting to Pupil Core...")
    pupil = pcnc.Device(address, port)
    pupil.send_notification({"subject": "frame_publishing.set_format", "format": "bgr"})
    print("Pupil Core Connected.")
    return pupil


def main():
    pupil = connect_to_pupil(pupil_address, pupil_port)

    loop = asyncio.get_event_loop()
    task = loop.create_task(run_server())
    gaze_thread = threading.Thread(target=receive_gaze_and_update_focus, args=(pupil, loop))
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
