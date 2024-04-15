import json
import urllib
from datetime import datetime
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

modes: dict[str, str] = {}  # mode for each client
envs: dict[str, EnvRunner] = {}  # EnvRunners for each client
peer_connections: dict[str, RTCPeerConnection] = {}  # RTCPeerConnections for each client

env_info = {
    "": {
        # "env_id": "FrankaPickPlaceMulti4Robots4Col-v0",
        "env_id": "FrankaPickPlaceMulti4Robots4Col-v1",
        "num_agents": 4,
    },
    "data-collection": {
        # "env_id": "FrankaPickPlaceSingle4Col-v0",
        "env_id": "FrankaPickPlaceSingle4Col-v1",
        "num_agents": 1,
    },
}


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "numAgents": env_info[""]["num_agents"],
        },
    )


@app.get("/data-collection")  # endpoint for data collection mode
async def data_collection(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "numAgents": env_info["data-collection"]["num_agents"],
        },
    )


@sio.event
async def connect(sid, environ):
    print("Client connected:", sid)
    query = urllib.parse.parse_qs(environ.get("QUERY_STRING", ""))
    endpoint = query.get("endpoint", [None])[0]
    print(f"endpoint: {endpoint}")

    if endpoint is None:
        return
    mode = endpoint[1:]
    if mode in env_info:
        env_id = env_info[mode]["env_id"]
        env = EnvRunner(env_id, sio)
        env.start()
        await sio.emit(
            "init",
            {
                "isDataCollection": mode == "data-collection",
                "commandLabels": env.command_labels,
                "commandColors": env.command_colors,
            },
            to=sid,
        )
        modes[sid] = mode
        envs[sid] = env
        peer_connections[sid] = createPeerConnection(sio)


@sio.event
async def disconnect(sid):
    print("Client disconnected:", sid)
    # delete env
    if sid in envs:
        await envs[sid].stop()
        del envs[sid]
    # close peer connection
    if sid in peer_connections:
        await peer_connections[sid].close()
        del peer_connections[sid]


@sio.on("taskReset")
async def task_reset(sid):
    if sid not in envs:
        return False
    await envs[sid].reset()
    return True


@sio.on("taskStop")
async def task_stop(sid):
    if sid not in envs:
        return False
    await envs[sid].clear_commands()
    return True


@sio.on("saveMetrics")
async def save_metrics(sid, data):
    if sid not in envs:
        return False
    env_id = env_info[modes[sid]]["env_id"]
    try:
        filepath = log_dir / env_id / data["username"] / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=4)
        print(f"Metrics saved to {filepath}")
        return True
    except Exception as e:
        print(f"Error saving metrics: {e}")
        print(f"data:\n{data}")
        return False


@sio.on("focus")
async def focus(sid, focus_id):
    print(f"focus: received {focus_id}")
    if sid not in envs:
        return False
    envs[sid].focus_id = focus_id


@sio.on("command")
async def command(sid, data: dict):
    if sid not in envs:
        return False
    agent_id = data["agentId"]
    command_label = data["command"]
    print(f"command: {command_label} for agent {agent_id}")
    await envs[sid].update_and_notify_command(command_label, agent_id)


@sio.on("webrtc-offer-request")
async def webrtc_offer_request(sid):
    if sid not in peer_connections:
        return False
    pc = peer_connections[sid]
    # add stream tracks
    relay = MediaRelay()
    for i in range(envs[sid].num_agents):
        track = relay.subscribe(ImageStreamTrack(envs[sid], i))
        pc.addTransceiver(track, direction="sendonly")
        print(f"Track {track.id} added to peer connection")

    await handle_offer_request(pc, sio)


@sio.on("webrtc-answer")
async def webrtc_answer(sid, data):
    if sid not in peer_connections:
        return False
    await handle_answer(peer_connections[sid], data)


@sio.on("webrtc-ice")
async def webrtc_ice(sid, data):
    if sid not in peer_connections:
        return False
    await handle_candidate(peer_connections[sid], data)


if __name__ == "__main__":
    log_dir = app_dir / "logs"
    key_dir = app_dir / "../.keys"  # for HTTPS

    uvicorn.run(
        socket_app,
        host="0.0.0.0",
        port=8000,
        ssl_keyfile=str(key_dir / "server.key"),
        ssl_certfile=str(key_dir / "server.crt"),
    )
