from pathlib import Path

import socketio
import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.app_state import AppState
from app.env import EnvRunner, ImageStreamTrack
from app.utils.webrtc import createPeerConnection, handle_answer, handle_candidate, handle_offer_request

app = FastAPI()
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")  # TODO
socket_app = socketio.ASGIApp(sio, other_asgi_app=app)

app_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=app_dir / "static"), name="static")
templates = Jinja2Templates(directory=app_dir / "templates")

app_state = AppState()  # global state for the app
env = EnvRunner(app_state)


@app.get("/")
async def get(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "num_agents": app_state.num_agents})


@sio.event
async def connect(sid, environ):
    print("Client connected:", sid)
    if not env.is_running:
        env.start()
    await sio.emit("init", {"classColors": env.class_colors, "numAgents": app_state.num_agents}, to=sid)


@sio.event
async def disconnect(sid):
    print("Client disconnected:", sid)
    if env.is_running:
        await env.stop()
    if app_state.pc:
        await app_state.pc.close()
        app_state.pc = None


@sio.on("keyup")
async def keyup(sid, key):
    print(f"keyup: received {key}")
    app_state.update_command("keyup", key)


@sio.on("keydown")
async def keydown(sid, key):
    print(f"keydown: received {key}")
    app_state.update_command("keydown", key)


@sio.on("focus")
async def focus(sid, focus_id):
    print(f"focus: received {focus_id}")
    app_state.focus = focus_id


@sio.on("eeg")
async def eeg(sid, command):
    print(f"eeg: received {command}")
    app_state.update_command("eeg", command)


@sio.on("webrtc-offer-request")
async def webrtc_offer_request(sid):
    pc = createPeerConnection(sio)
    app_state.pc = pc

    # add stream tracks
    for i in range(app_state.num_agents):
        track = app_state.relay.subscribe(ImageStreamTrack(env, i))
        pc.addTransceiver(track, direction="sendonly")
        print(f"Track {track.id} added to peer connection")

    await handle_offer_request(pc, sio)


@sio.on("webrtc-answer")
async def webrtc_answer(sid, data):
    await handle_answer(app_state.pc, data)


@sio.on("webrtc-ice")
async def webrtc_ice(sid, data):
    await handle_candidate(app_state.pc, data)


if __name__ == "__main__":
    # for HTTPS
    key_dir = app_dir / "../.keys"

    uvicorn.run(
        socket_app,
        host="0.0.0.0",
        port=8000,
        ssl_keyfile=key_dir / "server.key",
        ssl_certfile=key_dir / "server.crt",
    )
