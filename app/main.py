import os
import secrets
import urllib.parse
from datetime import datetime
from pathlib import Path

import socketio
import uvicorn
from aiortc import RTCPeerConnection
from aiortc.contrib.media import MediaRelay
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.env import EnvRunner, ImageStreamTrack
from app.utils.metrics import InteractionRecorder, compute_metrics, taskCompletionTimer
from app.utils.webrtc import createPeerConnection, handle_answer, handle_candidate, handle_offer_request

load_dotenv()

app = FastAPI()

secret_key = os.getenv("SESSION_SECRET_KEY")
if secret_key is None:
    secret_key = secrets.token_urlsafe(32)
    with open(Path(__file__).parent / ".env", "a") as f:
        f.write(f"SESSION_SECRET_KEY={secret_key}\n")
app.add_middleware(SessionMiddleware, secret_key=secret_key)

app_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=app_dir / "static"), name="static")
templates = Jinja2Templates(directory=app_dir / "templates")

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")  # TODO
socket_app = socketio.ASGIApp(sio, other_asgi_app=app)

envs: dict[str, EnvRunner] = {}  # EnvRunners for each mode
modes: dict[str, str] = {}  # mode for each client
peer_connections: dict[str, RTCPeerConnection] = {}  # RTCPeerConnections for each client
sid2ids: dict[str, str] = {}  # user id for each client that will be used to record interactions

# metrics
exp_ids: dict[str, str] = {}  # exp_id for each mode
task_completion_timers: dict[str, taskCompletionTimer] = {}  # taskCompletionTimer for each mode
interaction_recorders: dict[str, InteractionRecorder] = {}  # InteractionRecorder for each mode

env_info = {
    "data-collection": {
        "env_id": "FrankaPickPlaceSingle4Col-v1",
        "num_agents": 1,
    },
    "single-robot": {
        "env_id": "FrankaPickPlaceSingle4Col-v1",
        "num_agents": 1,
    },
    "multi-robot": {
        "env_id": "FrankaPickPlaceMulti4Robots4Col-v1",
        "num_agents": 4,
    },
}


@app.get("/register")
async def register(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {"request": request},
    )


@app.post("/api/setuser")
async def setuser(request: Request, userinfo: dict):
    # TODO: userinfo is basically validated in the frontend, but do it more strictly?
    request.session["userinfo"] = userinfo
    return True


@app.get("/api/getuser")
async def getuser(request: Request):
    return request.session.get("userinfo")


@app.get("/")
async def index(request: Request):
    if "userinfo" not in request.session:
        return RedirectResponse(url="/register")
    return templates.TemplateResponse(
        "index.html",
        {"request": request},
    )


async def task_page(request: Request, mode: str):
    if "userinfo" not in request.session:
        return RedirectResponse(url="/register")
    return templates.TemplateResponse(
        "app.html",
        {
            "request": request,
            "numAgents": env_info[mode]["num_agents"],
        },
    )


@app.get("/data-collection")
async def data_collection(request: Request):
    return await task_page(request, "data-collection")


@app.get("/single-robot")
async def single_robot(request: Request):
    return await task_page(request, "single-robot")


@app.get("/multi-robot")
async def multi_robot(request: Request):
    return await task_page(request, "multi-robot")


@sio.event
async def connect(sid, environ):
    print("Client connected:", sid)
    query = urllib.parse.parse_qs(environ.get("QUERY_STRING", ""))
    endpoint = query.get("endpoint", [None])[0]
    print(f"endpoint: {endpoint}")  # like "/multi-robot"

    mode = endpoint[1:]
    if mode not in env_info:
        return False

    # get existing env or create a new one
    if mode in envs:
        env = envs[mode]
    else:
        env = EnvRunner(
            env_info[mode]["env_id"],
            sio,
            on_completed=lambda: on_completed(mode),
        )
        envs[mode] = env

    # set exp_id if not set
    if mode not in exp_ids:
        exp_ids[mode] = datetime.now().strftime("%Y%m%d_%H%M%S")

    await sio.emit(
        "init",
        {
            "expId": exp_ids[mode],
            "isDataCollection": mode == "data-collection",
            "commandLabels": env.command_labels,
            "commandColors": env.command_colors,
        },
        to=sid,
    )
    modes[sid] = mode
    peer_connections[sid] = createPeerConnection(sio, sid)

    # send initial server status
    await sio.emit("status", {"isRunning": env.is_running}, to=sid)

    # create stuff for metrics
    interaction_recorders[mode] = InteractionRecorder()
    task_completion_timers[mode] = taskCompletionTimer()


@sio.event
async def disconnect(sid):
    print("Client disconnected:", sid)
    # close peer connection
    if sid in peer_connections:
        await peer_connections[sid].close()
        del peer_connections[sid]

    # remove mode entry
    assert sid in modes
    mode = modes[sid]
    del modes[sid]
    # Check if no other clients are using this mode
    if all(s != mode for s in modes.values()):
        # stop and delete the environment
        assert mode in envs
        await envs[mode].stop()
        del envs[mode]


def on_completed(mode: str):
    task_completion_timers[mode].stop()

    exp_id = exp_ids[mode]
    exp_log_dir = log_dir / exp_id
    exp_log_dir.mkdir(parents=True, exist_ok=True)

    info = {"total": {"taskCompletionTime": task_completion_timers[mode].elapsed}}
    # TODO?: add env/task information to info
    interaction_recorders[mode].save(exp_log_dir, info=info)

    compute_metrics(exp_log_dir, save=True)

    exp_ids.pop(mode)  # remove exp_id


@sio.on("taskStart")
async def task_start(sid, data):
    mode = modes[sid]
    env = envs[mode]

    # Initialize metrics and start env only for the first "start"
    if not env.is_running:
        interaction_recorders[mode].reset()
        task_completion_timers[mode].start()
        env.start()

    interaction_recorders[mode].add_user(
        data["userinfo"]["name"],
        {
            "userinfo": data["userinfo"],
            "deviceSelection": data["deviceSelection"],
        },
    )
    sid2ids[sid] = data["userinfo"]["name"]

    return True


@sio.on("taskStop")
async def task_stop(sid):
    mode = modes[sid]
    env = envs[mode]

    if env.is_running:
        await env.stop()
        await sio.emit("taskStopDone")  # notify clients that the env is stopped

    return True


@sio.on("focus")
async def focus(sid, focus_id):
    mode = modes[sid]
    print(f"focus: received {focus_id}")
    if mode not in envs:
        return False
    envs[mode].focus_id = focus_id


@sio.on("command")
async def command(sid, data: dict):
    mode = modes[sid]
    agent_id = data["agentId"]
    command_label = data["command"]
    print(f"command: {command_label} for agent {agent_id}")
    res = await envs[mode].update_and_notify_command(
        command_label,
        agent_id,
        data["likelihoods"],
        data["interactionTime"],
    )
    if res["interactionTime"] is not None:  # TODO: recording only acceptable interactions
        interaction_recorders[mode].record(
            sid2ids[sid],
            {
                "userId": sid2ids[sid],
                "agentId": res["agentId"],
                "command": res["command"],
                "isNowAcceptable": res["isNowAcceptable"],
                "hasSubtaskNotDone": res["hasSubtaskNotDone"],
                "likelihoods": res["likelihoods"],
                "interactionTime": res["interactionTime"],
            },
        )


@sio.on("webrtc-offer-request")
async def webrtc_offer_request(sid):
    pc = peer_connections[sid]
    mode = modes[sid]
    env = envs[mode]
    # add stream tracks
    relay = MediaRelay()
    for i in range(env.num_agents):
        track = relay.subscribe(ImageStreamTrack(env, i))
        pc.addTransceiver(track, direction="sendonly")
        print(f"Track {track.id} added to peer connection")

    await handle_offer_request(pc, sio, sid)


@sio.on("webrtc-answer")
async def webrtc_answer(sid, data):
    await handle_answer(peer_connections[sid], data)


@sio.on("webrtc-ice")
async def webrtc_ice(sid, data):
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
