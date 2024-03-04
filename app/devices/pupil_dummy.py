import asyncio
import random
from contextlib import asynccontextmanager

import socketio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

origins = [
    "http://localhost:8001",  # socket.io server (this app)
    "https://10.10.0.137:8000",  # browser client  # TODO: hard-coded
]

is_running = True
num_clients = 0
focus: int | None = None

num_agents = 3  # TODO: receive from the server


async def gaze_worker():
    global focus
    print("Gaze stream started")
    while is_running:
        if num_clients == 0:
            await asyncio.sleep(1)
            continue
        new_focus = random.randint(0, num_agents - 1)
        if new_focus != focus:
            focus = new_focus
            await sio.emit("gaze", {"focusId": focus})
            print(f"Sent focus: {focus}")
        await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    gaze_task = asyncio.create_task(gaze_worker())
    print("Gaze task started")

    yield

    gaze_task.cancel()
    try:
        await gaze_task
    except asyncio.CancelledError:
        print("Gaze task cancelled")


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
    uvicorn.run(socket_app, host="localhost", port=8001)
