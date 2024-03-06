import asyncio
from contextlib import asynccontextmanager

import pupil_labs.pupil_core_network_client as pcnc
import socketio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

pupil_address = "127.0.0.1"
pupil_port = 50020
origins = [
    "http://localhost:8001",  # socket.io server (this app)
    "https://localhost:8000",  # browser client
    "https://10.10.0.137:8000",  # TODO: hard-coded
]

is_running = True
num_clients = 0
focus: int | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    pupil = connect_to_pupil(pupil_address, pupil_port)
    gaze_task = asyncio.create_task(gaze_worker(pupil))
    print("Gaze task started")

    yield

    gaze_task.cancel()
    try:
        await gaze_task
    except asyncio.CancelledError:
        print("Gaze task cancelled")
    pupil.close()
    print("Pupil Core connection closed")


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=origins)
socket_app = socketio.ASGIApp(sio, other_asgi_app=app)


def connect_to_pupil(address: str, port: int):
    print("Connecting to Pupil Core...")
    pupil = pcnc.Device(address, port)
    pupil.send_notification({"subject": "frame_publishing.set_format", "format": "bgr"})
    print("Pupil Core Connected.")
    return pupil


async def gaze_worker(pupil):
    global is_running, focus

    with pupil.subscribe_in_background("surface", buffer_size=1) as sub:
        while is_running:
            if num_clients == 0:
                await asyncio.sleep(1)
                continue
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
                focus = new_focus
                await sio.emit("gaze", {"focusId": focus})
                print(f"Sent focus: {focus}")
            await asyncio.sleep(0.1)


def compute_focus_area(x, y):
    # (0, 0) is the bottom-left corner
    margin_vert = 0.3  # TODO: adjust margin
    if 0 <= x < 0.5:
        if 0.5 <= y <= 1 + margin_vert:
            return 0
        elif 0 - margin_vert <= y < 0.5:
            return 2
    elif 0.5 <= x <= 1:
        if 0.5 <= y <= 1 + margin_vert:
            return 1
        elif 0 - margin_vert <= y < 0.5:
            return 3

    return None


@sio.event
async def connect(sid, environ):
    global num_clients
    num_clients += 1
    print("Client connected:", sid)


@sio.event
async def disconnect(sid):
    global num_clients, focus
    num_clients -= 1
    print("Client disconnected:", sid)
    if num_clients == 0:
        focus = None  # reset focus


if __name__ == "__main__":
    uvicorn.run(socket_app, host="localhost", port=8001, lifespan="on")
