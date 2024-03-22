import asyncio
from contextlib import asynccontextmanager

import click
import numpy as np
import socketio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

is_running = True
num_clients = 0
# samp_rate = 30  # Hz
samp_rate = 10  # Hz


def gaze_generator():
    # TODO: make this more realistic
    pos = np.array([0.5, 0.5])  # (x, y)
    step_size = 0.05
    while True:
        yield {"x": pos[0], "y": pos[1]}
        step = np.random.uniform(-step_size, step_size, size=2)
        # pos = np.clip(pos + step, 0, 1)
        pos = np.clip(pos + step, 0.3, 0.7)  # limit gaze range


async def gaze_worker(sio: socketio.AsyncServer):
    print("Gaze stream started")
    gaze_gen = gaze_generator()
    while is_running:
        if num_clients == 0:
            await asyncio.sleep(1)
            continue
        gaze = next(gaze_gen)
        await sio.emit("gaze", gaze)
        await asyncio.sleep(1 / samp_rate)


@click.command()
@click.option("--env-ip", "-e", default="localhost", type=str, help="IP address of the environment server")
def main(env_ip):
    host = "localhost"
    port = 8001
    origins = [
        f"http://{host}:{port}",  # gaze server (this app)
        f"https://{env_ip}:8000",  # environment server
    ]

    sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=origins)

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

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        gaze_task = asyncio.create_task(gaze_worker(sio))
        print("Gaze task started")

        yield

        global is_running
        is_running = False
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
    socket_app = socketio.ASGIApp(sio, other_asgi_app=app)

    uvicorn.run(socket_app, host=host, port=port)


if __name__ == "__main__":
    main()
