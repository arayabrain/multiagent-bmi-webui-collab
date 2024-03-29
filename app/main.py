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
# env_id = "FrankaPickPlaceMulti4-v0"
env_id = "FrankaPickPlaceMulti4Robots4Col-v0"

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
            "commandLabels": env.command_labels,
            "commandColors": env.command_colors,
            "numAgents": env.num_agents,
        },
        to=sid,
    )


@sio.event
async def disconnect(sid):
    global pc
    print("Client disconnected:", sid)
    # reset env
    await env.reset()
    # close peer connection
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
        env.next_acceptable_commands[idx_agent].append("")  # TODO
        await env.update_and_notify_command("", idx_agent)
    return True


@sio.on("focus")
async def focus(sid, focus_id):
    print(f"focus: received {focus_id}")
    env.focus_id = focus_id


@sio.on("command")
async def command(sid, data: dict):
    agent_id = data["agentId"]
    command_label = data["command"]
    print(f"command: {command_label} for agent {agent_id}")
    await env.update_and_notify_command(command_label, agent_id)


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
