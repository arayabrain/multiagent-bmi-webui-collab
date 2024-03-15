from pathlib import Path

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

# env_id = "FrankaReachFixedMulti-v0"
# env_id = "FrankaPickPlaceMulti-v0"
env_id = "FrankaPickPlaceMulti4-v0"
env = EnvRunner(env_id, sio)

pc: RTCPeerConnection | None = None
relay = MediaRelay()  # use the same instance for all connections


@app.get("/")
async def get(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "num_agents": env.num_agents,
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
            "numAgents": env.num_agents,
        },
        to=sid,
    )


@sio.event
async def disconnect(sid):
    global pc
    print("Client disconnected:", sid)
    # env does not stop
    if pc:
        await pc.close()
        pc = None


@sio.on("taskReset")
async def task_reset(sid):
    await env.reset()
    return True


@sio.on("taskStop")
async def task_stop(sid):
    # just reset the command
    # TODO: capsulate this in env
    for idx_agent in range(env.num_agents):
        await env._update_and_notify_command(None, idx_agent)
    return True


@sio.on("keyup")
async def keyup(sid, key):
    print(f"keyup: received {key}")
    await env.update_command("keyup", key)


@sio.on("keydown")
async def keydown(sid, key):
    print(f"keydown: received {key}")
    await env.update_command("keydown", key)


@sio.on("focus")
async def focus(sid, focus_id):
    print(f"focus: received {focus_id}")
    env.focus_id = focus_id


@sio.on("eeg")
async def eeg(sid, command):
    print(f"eeg: received {command}")
    await env.update_command("eeg", command)


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
