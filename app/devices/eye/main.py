import asyncio
from contextlib import asynccontextmanager

import click
import pupil_labs.pupil_core_network_client as pcnc
import socketio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

is_running = True
num_clients = 0
# samp_rate = 30  # Hz; too fast, causing delays
samp_rate = 10
# samp_rate = 5
confidence_threshold = 0.7

def connect_to_pupil(address: str, port: int):
    print("Connecting to Pupil Core...")
    pupil = pcnc.Device(address, port)
    pupil.send_notification({"subject": "frame_publishing.set_format", "format": "bgr"})
    print("Pupil Core Connected.")
    return pupil

async def gaze_worker(pupil, sio: socketio.AsyncServer):
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
            # gaze = message.payload["fixations_on_surfaces"]
            if not gaze:
                continue

            # use only the latest gaze
            # (x, y) in [0, 1]^2; origin is at the bottom-left
            x, y = gaze[-1]["norm_pos"]
            conf = gaze[-1]["confidence"]

            print(f"confidence={conf:.02f}, x={gaze[-1]['norm_pos'][0]:.02f}, y={gaze[-1]['norm_pos'][1]:.02f}")
            if conf < confidence_threshold:
                continue
            if x < 0 or x > 1 or y < 0 or y > 1:
                continue

            # TODO: noise reduction and smoothing?

            await sio.emit("gaze", {"x": x, "y": 1 - y})  # convert origin to top-left
            await asyncio.sleep(1 / samp_rate)

@click.command()
@click.option("--env-ip", "-e", default="localhost", type=str, help="IP address of the environment server")
def main(env_ip):
    pupil_address = "127.0.0.1"
    pupil_port = 50020
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
        pupil = connect_to_pupil(pupil_address, pupil_port)
        gaze_task = asyncio.create_task(gaze_worker(pupil, sio))
        print("Gaze task started")

        yield

        global is_running
        is_running = False
        gaze_task.cancel()
        try:
            await gaze_task
        except asyncio.CancelledError:
            print("Gaze task cancelled")
        pupil.disconnect()
        print("Pupil Core disconnected")

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
