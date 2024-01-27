import asyncio
import json
from typing import Dict, List

import gym
import numpy as np
import robohive.envs.arms  # noqa: F401 # type: ignore
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.contrib.media import MediaRelay
from aiortc.sdp import candidate_from_sdp
from av import VideoFrame
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

n_chs = 128
num_agents = 4

env = gym.make("FrankaReachFixedMulti-v0")
a_dim_per_agent = env.action_space.shape[0] // num_agents

command: List[int] = [0] * num_agents
focus: int | None = None  # updated only by websocket_endpoint_browser
frames: List[np.ndarray | None] = [None] * num_agents
frame_update_cond = asyncio.Condition()
relay = MediaRelay()  # keep using the same instance for all connections

ws_clients: Dict[str, WebSocket] = {}
peer_connections: Dict[str, RTCPeerConnection] = {}
data_channels: Dict[str, RTCPeerConnection] = {}


@app.get("/")
async def get(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "num_agents": num_agents})


def createPeerConnection(websocket: WebSocket):
    # WebRTC connection
    pc = RTCPeerConnection()
    peer_connections["camera"] = pc
    track_ids: List[str] = []

    @pc.on("icecandidate")
    async def on_icecandidate(candidate):
        print("/browser: sending ice candidate info")
        data = {
            "type": "webrtc-ice",
            "candidate": None,
        }
        if candidate:
            data["candidate"] = {
                "candidate": candidate.to_sdp(),
                "sdpMid": candidate.sdpMid,
                "sdpMLineIndex": candidate.sdpMLineIndex,
            }
        await websocket.send_json(data)

    @pc.on("connectionstatechange")
    def on_connectionstatechange():
        print(f"/browser: connection state: {pc.connectionState}")

    @pc.on("iceconnectionstatechange")
    def on_iceconnectionstatechange():
        print(f"/browser: ice connection state: {pc.iceConnectionState}")

    # initialize tracks
    for i in range(num_agents):
        track = relay.subscribe(ImageStreamTrack(i))
        pc.addTrack(track)
        print(f"Track {track.id} added to peer connection")
        track_ids.append(track.id)

    return pc, track_ids


async def handle_candidate(pc, data):
    print("/browser: received ice candidate info")
    if data["candidate"] is None:
        # candidate is None when all candidates have been received
        print("/browser: all candidates received")
        # await pc.addIceCandidate(None)  # error
    else:
        candidate = candidate_from_sdp(data["candidate"])
        candidate.sdpMid = data["sdpMid"]
        candidate.sdpMLineIndex = data["sdpMLineIndex"]
        await pc.addIceCandidate(candidate)


@app.websocket("/browser")
async def ws_browser(websocket: WebSocket):
    """Websocket endpoint for browser client

    Args:
        websocket (WebSocket): websocket connection from browser
    """
    global focus

    await websocket.accept()
    ws_clients["browser"] = websocket
    print("/browser: Client connected")

    # run environment
    task = asyncio.create_task(env_process())

    try:
        while True:
            data = await websocket.receive_json()

            if data["type"] in ("keyup", "keydown"):
                print(f"/browser: received {data}")
                update_command(data)
            elif data["type"] == "focus":
                print(f"/browser: received {data}")
                focus = data["focusId"]

            elif data["type"] == "webrtc-offer-request":
                print(f"/browser: received {data}")
                pc, track_ids = createPeerConnection(websocket)

                offer = await pc.createOffer()
                await websocket.send_json(
                    {
                        "type": "webrtc-offer",
                        "sdp": offer.sdp,
                        "trackIds": track_ids,
                    }
                )
                print("/browser: sent webrtc-offer")
                await pc.setLocalDescription(offer)  # slow; takes 5s
                print("/browser: set local description")
            elif data["type"] == "webrtc-answer":
                print("/browser: received webrtc-answer")
                await pc.setRemoteDescription(RTCSessionDescription(type="answer", sdp=data["sdp"]))
            elif data["type"] == "webrtc-ice":
                await handle_candidate(pc, data)

    except WebSocketDisconnect:
        print("/browser: Client disconnected")
        task.cancel()  # env state is preserved since it's a global variable


# TODO: zeromq
@app.websocket("/pupil")
async def ws_pupil(websocket: WebSocket):
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


# TODO: zeromq
@app.websocket("/webrtc-eeg")
async def ws_eeg_webrtc(websocket: WebSocket):
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


class ImageStreamTrack(VideoStreamTrack):
    def __init__(self, camera_idx: int):
        super().__init__()
        self.camera_idx = camera_idx

    async def recv(self):
        global frames

        async with frame_update_cond:
            await frame_update_cond.wait()
            frame = frames[self.camera_idx]

        # img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = frame
        frame = VideoFrame.from_ndarray(img, format="rgb24")
        pts, time_base = await self.next_timestamp()
        frame.pts = pts
        frame.time_base = time_base

        return frame


# TODO: separate thread?
async def env_process():
    print("env_process started")
    global frames

    # init
    obs = env.reset()

    while True:
        action = get_action(obs, command)
        obs, _, done, _ = env.step(action)
        visuals = env.get_visuals()

        async with frame_update_cond:
            for i in range(num_agents):
                frames[i] = visuals[f"rgb:franka{i}_front_cam:256x256:1d"].reshape((256, 256, 3))
            frame_update_cond.notify_all()

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
