from pathlib import Path

import gym
import socketio
import uvicorn
from aiortc import RTCPeerConnection
from aiortc.contrib.media import MediaRelay
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.env import EnvRunner, ImageStreamTrack
from app.utils.webrtc import createPeerConnection, handle_answer, handle_candidate, handle_offer_request

app = FastAPI()
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")  # TODO
socket_app = socketio.ASGIApp(sio, other_asgi_app=app)

app_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=app_dir / "static"), name="static")
templates = Jinja2Templates(directory=app_dir / "templates")

# constants
# env_id = "FrankaReachFixedMulti-v0"
# env_id = "FrankaPickPlaceMulti-v0"
env_id = "FrankaPickPlaceMulti4-v0"

gym_env = gym.make(env_id)
num_agents = gym_env.nrobots

# global states for the app
command: list[int] = [0] * num_agents
focus_id: int | None = None  # updated only by websocket_endpoint_browser
env = EnvRunner(gym_env, command)
pc: RTCPeerConnection | None = None
relay = MediaRelay()  # use the same instance for all connections


@app.get("/")
async def get(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "num_agents": num_agents,
        },
    )


@sio.event
async def connect(sid, environ):
    print("Client connected:", sid)
    if not env.is_running:
        env.start()
    await sio.emit(
        "init",
        {
            "class2color": env.class2color,
            "numAgents": num_agents,
        },
        to=sid,
    )


@sio.event
async def disconnect(sid):
    global pc
    print("Client disconnected:", sid)
    if env.is_running:
        await env.stop()
    if pc:
        await pc.close()
        pc = None


@sio.on("keyup")
async def keyup(sid, key):
    print(f"keyup: received {key}")
    update_command("keyup", key)


@sio.on("keydown")
async def keydown(sid, key):
    print(f"keydown: received {key}")
    update_command("keydown", key)


@sio.on("focus")
async def focus(sid, new_focus_id):
    global focus_id
    print(f"focus: received {new_focus_id}")
    focus_id = new_focus_id


@sio.on("eeg")
async def eeg(sid, command):
    print(f"eeg: received {command}")
    update_command("eeg", command)


def update_command(event, data):
    if focus_id is None:
        return
    if event == "eeg":
        # assume data is a command
        command[focus_id] = data
    elif event == "keydown":
        # assume data is a key
        if data == "0":
            command[focus_id] = 0
        elif data in ("1", "2", "3"):
            command[focus_id] = 1


@sio.on("webrtc-offer-request")
async def webrtc_offer_request(sid):
    global pc
    pc = createPeerConnection(sio)

    # add stream tracks
    for i in range(env.num_agents):
        track = relay.subscribe(ImageStreamTrack(env, i))
        pc.addTransceiver(track, direction="sendonly")
        print(f"Track {track.id} added to peer connection")

    await handle_offer_request(pc, sio)


@sio.on("webrtc-answer")
async def webrtc_answer(sid, data):
    await handle_answer(pc, data)


@sio.on("webrtc-ice")
async def webrtc_ice(sid, data):
    await handle_candidate(pc, data)


if __name__ == "__main__":
    # for HTTPS
    key_dir = app_dir / "../.keys"

    uvicorn.run(
        socket_app,
        host="0.0.0.0",
        port=8000,
        ssl_keyfile=str(key_dir / "server.key"),
        ssl_certfile=str(key_dir / "server.crt"),
    )
