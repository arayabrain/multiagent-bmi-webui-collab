import asyncio
import base64
import json
from io import BytesIO
from typing import Dict, List

import gym
import numpy as np
import robohive.envs.arms  # noqa: F401 # type: ignore
from aiortc import RTCPeerConnection, RTCSessionDescription
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

num_agents = 4
env = gym.make("FrankaReachFixedMulti-v0")
a_dim_per_agent = env.action_space.shape[0] // num_agents
command: List[int] = [0] * num_agents

ws_clients: Dict[str, WebSocket] = {}
focus: int | None = None  # updated only by websocket_endpoint_browser

# WebRTC
peer_connections: Dict[str, RTCPeerConnection] = {}
data_channels: Dict[str, RTCPeerConnection] = {}

n_chs = 128


@app.get("/")
async def get(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "num_agents": num_agents})


@app.websocket("/browser")
async def websocket_endpoint_browser(websocket: WebSocket):
    global focus

    await websocket.accept()
    ws_clients["browser"] = websocket
    print("/browser: Client connected")

    # run environment
    task = asyncio.create_task(env_process(websocket))

    try:
        while True:
            data = await websocket.receive_json()
            print(f"/browser: received {data}")

            if data["type"] in ("keyup", "keydown"):
                update_command(data)
            elif data["type"] == "focus":
                focus = data["focusId"]
    except WebSocketDisconnect:
        print("/browser: Client disconnected")
        task.cancel()  # env state is preserved since it's a global variable


@app.websocket("/pupil")
async def websocket_endpoint_pupil(websocket: WebSocket):
    await websocket.accept()
    ws_clients["pupil"] = websocket
    print("/pupil: Client connected")
    try:
        while True:
            data = await websocket.receive_json()
            print(f"/pupil: received {data}")
            # transfer the focus info to browser
            await ws_clients["browser"].send_json(data)
    except WebSocketDisconnect:
        print("/pupil: Client disconnected")


@app.websocket("/webrtc-eeg")
async def websocket_endpoint_eeg(websocket: WebSocket):
    await websocket.accept()
    print("/webrtc-eeg: Client connected")
    try:
        # setup WebRTC connection
        print("/webrtc-eeg: Setting up WebRTC connection...")
        # receive offer
        offer = json.loads(await websocket.receive_text())
        # setup peer connection
        pc = RTCPeerConnection()
        await pc.setRemoteDescription(RTCSessionDescription(sdp=offer["sdp"], type="offer"))
        # send answer
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        await websocket.send_text(
            json.dumps(
                {
                    "type": "answer",
                    "sdp": pc.localDescription.sdp,
                }
            )
        )

        # set the event handlers for data channel
        @pc.on("datachannel")
        def on_datachannel(channel):
            data_channels["eeg"] = channel

            @channel.on("message")
            def on_message(message):
                assert isinstance(message, bytes)
                eeg_data = np.frombuffer(message, dtype=np.float32).reshape(n_chs, -1)
                print(f"/webrtc-eeg: received eeg {eeg_data.shape}")

                # TODO
                # decode to command
                command = np.random.randint(0, 4)
                # update command
                update_command({"type": "eeg", "command": command})  # TODO

        peer_connections["eeg"] = pc

    except WebSocketDisconnect:
        print("/webrtc-eeg: Client disconnected")
        pc = peer_connections.pop("eeg", None)
        if pc is not None:
            await pc.close()
        data_channels.pop("eeg", None)


def update_command(data):
    global command, focus

    if focus is None:
        return

    if data["type"] == "eeg":
        command[focus] = data["command"]
    elif data["type"] == "keydown":
        if data["key"] == "0":
            command[focus] = 0
        elif data["key"] in ("1", "2", "3"):
            command[focus] = 1


# TODO: separate thread?
async def env_process(websocket: WebSocket):
    print("env_process started")

    # init
    obs = env.reset()

    while True:
        action = get_action(obs, command)
        obs, _, done, _ = env.step(action)
        visuals = env.get_visuals()

        for i in range(num_agents):
            img = visuals[f"rgb:franka{i}_front_cam:256x256:1d"].reshape((256, 256, 3))
            # encode
            buffered = BytesIO()
            img = Image.fromarray(img)
            img.save(buffered, format="JPEG")
            img_str = base64.b64encode(buffered.getvalue()).decode()

            # send to client
            await websocket.send_json({"type": "image", "data": img_str, "id": f"camera_{i}"})

        if done:
            env.reset()

        await asyncio.sleep(0.03)


def get_action(obs, command):
    # TODO: use policy

    action = env.action_space.sample()
    # zero actions for agents with command 0
    for i in range(num_agents):
        if command[i] == 0:
            action[i * a_dim_per_agent : (i + 1) * a_dim_per_agent] = 0

    return action


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", reload=True)
