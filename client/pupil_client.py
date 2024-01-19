import asyncio
import json

import pupil_labs.pupil_core_network_client as pcnc
import websockets

is_running = True
focus = None
lock = asyncio.Lock()


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


async def receive_gaze_and_update_focus():
    global is_running, focus

    with pupil.subscribe_in_background("fixation", buffer_size=1) as sub:
        while is_running:
            message = sub.recv_new_message()
            x, y = message.payload["norm_pos"]
            new_focus = compute_focus_area(x, y)
            async with lock:
                focus = new_focus


async def send_focus():
    global is_running, focus
    uri = "ws://localhost:8000/ws/input"

    async with websockets.connect(uri) as websocket:
        prev_focus = None
        while is_running:
            async with lock:
                if focus != prev_focus:
                    data = {"type": "gaze", "focus_id": focus}
                    await websocket.send(json.dumps(data))
                    prev_focus = focus
            await asyncio.sleep(0.1)  # TODO


async def main():
    t1 = asyncio.create_task(receive_gaze_and_update_focus())
    t2 = asyncio.create_task(send_focus())
    await asyncio.gather(t1, t2)


if __name__ == "__main__":
    address = "127.0.0.1"
    port = 50020
    pupil = pcnc.Device(address, port)
    pupil.send_notification({"subject": "frame_publishing.set_format", "format": "bgr"})

    asyncio.run(main())
