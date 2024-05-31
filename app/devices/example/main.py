"""
This is a template of how to create a device server for a custom device.
See eye/main.py for a actual example.
"""

import asyncio
from contextlib import asynccontextmanager

import click
import socketio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

device_name = "Your Device"
event_name = "your_device"
samp_rate = 10  # Hz

is_running = True
num_clients = 0


def connect_to_device(address: str, port: int):
    """Connect to your device"""
    print(f"Connecting to {device_name}...")

    # connect to the device
    device = ...

    print(f"{device_name} Connected.")
    return device


async def worker(device, sio: socketio.AsyncServer):
    while is_running:
        # wait until at least one client is connected
        if num_clients == 0:
            await asyncio.sleep(1)
            continue

        # get the next data from the device
        data = device.get_next_data()

        # process/decode the data
        # for robot selection devices, it's like {"x": 0.2, "y": 0.3}
        # for subtask selection devices, it's like {"classId": 0, "likelihoods": [0.5, 0.3, 0.2]}
        data_to_send = ...

        await sio.emit(event_name, data_to_send)
        await asyncio.sleep(1 / samp_rate)


@click.command()
@click.option("--env-ip", "-e", default="localhost", type=str, help="IP address of the environment server")
def main(env_ip):
    device_address = "127.0.0.1"
    device_port = 12345
    host = "localhost"
    port = 1234
    origins = [
        f"http://{host}:{port}",  # device server (this app)
        f"https://{env_ip}:8000",  # environment server
    ]

    # create the SocketIO server
    sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=origins)

    @sio.event
    async def connect(sid, environ):
        # This function will be called automatically by SocketIO when a client connects
        global num_clients
        num_clients += 1
        print("Client connected:", sid)

    @sio.event
    async def disconnect(sid):
        # This function will be called automatically by SocketIO when a client disconnects
        global num_clients, focus
        num_clients -= 1
        print("Client disconnected:", sid)
        if num_clients == 0:
            focus = None  # reset focus

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # This function will be called automatically by FastAPI at startup

        # on startup
        # connect to the device
        device = connect_to_device(device_address, device_port)
        # start the worker
        task = asyncio.create_task(worker(device, sio))
        print(f"{device_name} task started")

        yield

        # on shutdown
        # cancel the task
        global is_running
        is_running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            print(f"{device_name} task cancelled")
        # disconnect from the device
        device.disconnect()
        print(f"{device_name} disconnected")

    # create the FastAPI app
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
