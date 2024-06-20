import asyncio
import os
import secrets
import string
import urllib.parse
from datetime import datetime
from pathlib import Path

import socketio
import uvicorn
from aiortc import RTCPeerConnection
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from typing import Dict, List

from app.env import EnvRunner
from app.stream import StreamManager
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

envs: Dict[str, EnvRunner] = {}  # EnvRunners for each mode
stream_manager = StreamManager()  # manage streams for each mode

modes: Dict[str, str] = {}  # mode for each client
envs: Dict[str, EnvRunner] = {}  # EnvRunners for each client
peer_connections: Dict[str, RTCPeerConnection] = {}  # RTCPeerConnections for each client

sid2userid: Dict[str, str] = {} # user_i d for each sid
connectedUsers: List = [] # list of users that registered in their browsers
exp_ids: Dict[str, str] = {}  # exp_id for each mode
task_completion_timers: Dict[str, taskCompletionTimer] = {}  # taskCompletionTimer for each mode
interaction_recorders: Dict[str, InteractionRecorder] = {} 

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
countdown_sec = 3


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
    connectedUsers.append(userinfo["name"])
    return True

@app.post("/api/save-nasa-tlx-data")
async def save_nasa_tlx_data(request: Request, survey_data: dict):
    # TODO: survey data saving
    # - where do we store it ? which logs forlder ?
    # - what should the file name be ? project_id/session_id/username_YYYYMMDD/device_1_device_2__nasatlx.json ?
    # - save as JSON dict ?
    # - anything else we need that is not in survey_data ?
    return True

@app.get("/api/getuser")
async def getuser(request: Request):
    return request.session.get("userinfo")


@app.get("/")
async def index(request: Request):
    if "userinfo" not in request.session:
        return RedirectResponse(url="/register")

    flash = request.session.pop("flash", None)
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "flash": flash},
    )


async def task_page(request: Request, mode: str):
    if "userinfo" not in request.session:
        return RedirectResponse(url="/register")

    # restrict users from joining in the middle of an experiment
    if mode in envs and envs[mode].is_running:
        request.session["flash"] = {
            "message": "The experiment is already running.\nPlease wait for it to finish.",
            "category": "warning",
        }
        return RedirectResponse(url="/")

    return templates.TemplateResponse(
        "app.html",
        {
            "request": request,
            "numAgents": env_info[mode]["num_agents"],
        },
    )


async def survey_page(request: Request, mode: str):
    if "userinfo" not in request.session:
        return RedirectResponse(url="/register")
    
    # TODO: shared same func "task_page" for serving ?
    # TODO: might want to check that (valid) devices
    # are set, otherwise the data saved might be useless
    return templates.TemplateResponse(
        "nasa-tlx-survey.html",
        {
            "request": request
        }
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


@app.get("/nasa-tlx-survey")
async def nasa_tlx_survey(request: Request):
    return await survey_page(request, "nasa-tlx-survery")


@sio.event
async def connect(sid, environ):
    print("Client connected:", sid)

    # generate user id
    alphabet = string.ascii_uppercase + string.digits
    user_id = "".join(secrets.choice(alphabet) for _ in range(8))
    sid2userid[sid] = user_id

    # get mode
    query = urllib.parse.parse_qs(environ.get("QUERY_STRING", ""))
    endpoint = query.get("endpoint", [None])[0]
    print(f"endpoint: {endpoint}")  # like "/multi-robot"
    mode = endpoint[1:] #get mode here for connect

    if mode not in env_info:
        return False

    # get or create env
    if mode in envs:
        env = envs[mode]
    else:
        env = EnvRunner(
            env_info[mode]["env_id"],
            notify_fn=lambda event, data: sio.emit(event, data, room=mode),
            on_completed_fn=lambda: asyncio.create_task(on_completed(mode)),
            )
        if mode == "data-collection":
            mode = mode + user_id
        envs[mode] = env
        stream_manager.setup(mode, env.env.get_visuals, env.num_agents)

    # set exp_id if not set
    if mode not in exp_ids:
        exp_ids[mode] = datetime.now().strftime("%Y%m%d_%H%M%S") #experiment ids are shared between clients if in same mode.

    await sio.emit(
        "init",
        {
            "expId": exp_ids[mode],
            "isDataCollection": mode.startswith("data-collection"),
            "commandLabels": env.command_labels,
            "commandColors": env.command_colors,
        },
        to=sid,
    )
    modes[sid] = mode
    await sio.enter_room(sid, mode)

    peer_connections[sid] = createPeerConnection(sio, sid) #HD

    # get or create metrics
    if mode not in interaction_recorders:
        interaction_recorders[mode] = InteractionRecorder()
    if mode not in task_completion_timers:
        task_completion_timers[mode] = taskCompletionTimer()

    # send initial server status
    await sio.emit("status", "Ready.", to=sid)

    # Broadcast the updated list of connected user IDs to all clients
    # await sio.emit("user_list_update", list(sid2userid.values()))
    await sio.emit("user_list_update", connectedUsers)


@sio.event
async def disconnect(sid):
    print("Client disconnected:", sid)
    # remove id
    if sid in sid2userid:
        del sid2userid[sid]

    # close peer connection
    if sid in peer_connections:
        await peer_connections[sid].close()
        del peer_connections[sid]

    # remove mode entry
    assert sid in modes
    mode = modes[sid]
    del modes[sid]

    # Check if no other clients are using this mode
    if all(m != mode for m in modes.values()):
        # cleanup streams
        await stream_manager.cleanup(mode)
        # stop and delete the environment
        if envs[mode].is_running:
            await envs[mode].stop()
        del envs[mode]
        print(f"Environment for {mode} is deleted")
        # delete metrics
        del interaction_recorders[mode]
        del task_completion_timers[mode]

    await sio.emit("user_list_update", connectedUsers) 


async def on_completed(mode: str):
    task_completion_timers[mode].stop()

    exp_id = exp_ids.pop(mode)
    exp_log_dir = log_dir / exp_id
    exp_log_dir.mkdir(parents=True, exist_ok=True)

    info = {"total": {"taskCompletionTime": task_completion_timers[mode].elapsed}}
    # TODO?: add env/task information to info
    interaction_recorders[mode].save(exp_log_dir, info=info)
    compute_metrics(exp_log_dir, save=True)

    await _server_stop(mode, is_completed=True)


@sio.on("addUser")
async def add_user(sid, data):
    # NOTE: call this after "taskStartRequested" since the interaction recorder is reset at the start
    mode = modes[sid]
    interaction_recorders[mode].add_user(sid2userid[sid], data)
    return True


@sio.on("requestServerStart")
async def server_start(sid):
    mode = modes[sid]
    env = envs[mode]
    assert not env.is_running

    # Initialize metrics and start env
    interaction_recorders[mode].reset()
    task_completion_timers[mode].start()
    # start all clients in the mode
    await sio.emit("requestClientStart", room=mode)
    env.start()

    # countdown
    for i in range(countdown_sec, 0, -1):
        await sio.emit("status", f"Start in {i} sec...", room=mode)
        await asyncio.sleep(1)

    await sio.emit("serverStartDone", room=mode)
    await sio.emit("status", "Running...", room=mode)

    return True


@sio.on("requestServerStop")
async def server_stop(sid, is_completed: bool = False):
    return await _server_stop(modes[sid], is_completed)


async def _server_stop(mode, is_completed: bool = False):
    env = envs[mode]
    assert env.is_running
    await env.stop()
    await sio.emit("requestClientStop", is_completed, room=mode)  # notify clients that the env is stopped
    await sio.emit("status", "Completed!" if is_completed else "Stopped.", room=mode)
    return True



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
        res.pop("nextAcceptableCommands")  # delete unnecessary item
        interaction_recorders[mode].record(sid2userid[sid], res)


@sio.on("webrtc-offer-request")
async def webrtc_offer_request(sid):
    pc = peer_connections[sid]
    mode = modes[sid]
    # add stream tracks
    tracks = stream_manager.get_tracks(mode)
    for track in tracks:
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
