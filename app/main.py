import asyncio
import json
import multiprocessing as mp
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
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from typing import Dict, List

from app.env import EnvRunner
from app.stream import StreamManager
from app.utils.metrics import InteractionRecorder, compute_sessionmetrics, compute_usermetrics, taskCompletionTimer
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

sid2userid: Dict[str, str] = {}  # user_i d for each sid
sid2username: Dict[str, str] = {}  # user_name for each sid
connectedUsers: List = []  # list of users that registered in their browsers
mode2expids: Dict[str, str] = {}  # exp_id for each mode
task_completion_timers: Dict[str, taskCompletionTimer] = {}  # taskCompletionTimer for each mode
interaction_recorders: Dict[str, InteractionRecorder] = {}
uniq_client_sids: Dict[str, Dict] = {}  # Uniquely id a browser session (tab ?), track user info if applicable.

env_info = {
    "data-collection": {
        "env_id": "FrankaPickPlaceSingle4Col-v1",
        "num_agents": 1,
    },
    "single-robot": {
        "env_id": "FrankaProcedural1Robots4Col-v0",
        "num_agents": 1,
    },
    "multi-robot-4": {
        "env_id": "FrankaProcedural4Robots4Col-v0",
        "num_agents": 4,
    },
    "multi-robot-16": {
        "env_id": "FrankaProcedural16Robots4Col-v0",
        "num_agents": 16
    },
}
countdown_sec = 3

# Helpers for tracking a specific user across browser sessions
## Tracking a user based on the browser cookie
def get_uniq_client_sid(request: Request):
    """
        This was just from observation, not necessarily a convention.
        On each browser that has a request, cookies["session"] looks like:
        "eyJ1c2....QifX0=.Zourmg.3A_sTgiS5bLKd_i8AuloEAHCHzs"
        For a given browser, the string before the first "." stays the same

        NOTE: This will also globally track all the browsers that issued a request
        TODO: there is no session when logging in with InPrivate for example,
        so how to recover it once it is properly created ? Although as soon as the user registers
        and redirected to index, will have this available ?
    """
    uniq_cli_sid = None
    if "session" in request.cookies.keys():
        uniq_cli_sid = request.cookies["session"].split(".")[0]
        if uniq_cli_sid not in list(uniq_client_sids.keys()):
            uniq_client_sids[uniq_cli_sid] = {}  # Placeholder for user info, etc...
    else:
        print("#### DBG: session witout cookie")

    # DBG
    print("")
    print("#### DBG Client Sessions")
    for idx, client_session in enumerate(uniq_client_sids.keys()):
        print(f"  {idx} -> {client_session}")
    print("")

    return uniq_cli_sid


@app.get("/register")
async def register(request: Request):
    get_uniq_client_sid(request)
    return templates.TemplateResponse(
        "register.html",
        {"request": request},
    )


@app.post("/api/setuser")
async def setuser(request: Request, userinfo: dict):
    print("")
    print("##### DBG BFR: all users data at register #####")
    print(f"New user with info: {userinfo}")
    print(f"Connected users info: {connectedUsers}")
    print(f"Modes: {modes}")
    print(f"sid2userid: {sid2userid}")
    print(f"sid2username: {sid2username}")
    print(f"mode2expids: {mode2expids}")
    print("##### DEBUG END: all users data at register #####")
    print("")
    # TODO: userinfo is basically validated in the frontend, but do it more strictly?
    request.session["userinfo"] = userinfo
    username = userinfo["name"]

    if username in connectedUsers:
        # NOTE: this type of errors handling is quite naive,
        # but we probably won't go into advanced form checks anyway.
        raise HTTPException(
            status_code=400,
            detail={
                "errors": ["username-already-registered"]
            }
        )

    connectedUsers.append(userinfo["name"])

    print("")
    print("##### DBG AFTR: all users data at register #####")
    print(f"New user with info: {userinfo}")
    print(f"Connected users info: {connectedUsers}")
    print(f"Modes: {modes}")
    print(f"sid2userid: {sid2userid}")
    print(f"sid2username: {sid2username}")
    print(f"mode2expids: {mode2expids}")
    print("##### DEBUG END: all users data at register #####")
    print("")

    return True

@app.post("/api/save-nasa-tlx-data")
async def save_nasa_tlx_data(request: Request, survey_data: dict):
    mode = survey_data['mode']

    username = survey_data['userinfo']['name']
    sub_log_dir = log_dir / f"{username}"
    sub_log_dir.mkdir(parents=True, exist_ok=True)


    time_id = mode2expids[mode]
    session_name = f"{time_id}" #might want to make bids format

    survey_path = sub_log_dir / session_name
    survey_path.mkdir(parents=True, exist_ok=True)

    #remove fields other than survey data
    saved_data = survey_data.copy()
    keys_to_remove = ['mode', 'userinfo', 'device-selection']
    for key in keys_to_remove:
        saved_data.pop(key, None)

    file_name = "nasatlx.json"
    with open(survey_path / file_name, mode="w") as f:
        json.dump(saved_data, f, indent=4)

    return True

@app.get("/api/getuser")
async def getuser(request: Request):
    return request.session.get("userinfo")


@app.get("/")
async def index(request: Request):
    get_uniq_client_sid(request) # Tracking uniq user

    if "userinfo" not in request.session:
        return RedirectResponse(url="/register")

    flash = request.session.pop("flash", None)
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "flash": flash},
    )


async def task_page(request: Request, mode: str):
    get_uniq_client_sid(request) # Tracking uniq user

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
    get_uniq_client_sid(request) # Tracking uniq user

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

@app.get("/multi-robot-4")
async def multi_robot(request: Request):
    return await task_page(request, "multi-robot-4")

@app.get("/multi-robot-16")
async def multi_robot_16(request: Request):
    return await task_page(request, "multi-robot-16")

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
            num_agents=env_info[mode]["num_agents"],
            notify_fn=lambda event, data: sio.emit(event, data, room=mode),
            on_completed_fn=lambda: asyncio.create_task(on_completed(mode)),
            )
        if mode == "data-collection":
            mode = mode + user_id
        envs[mode] = env
        stream_manager.setup(mode, env.env.get_visuals, env.num_agents)

    await sio.emit(
        "init",
        {
            #"expId": mode2expids[mode],
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

    # TODO: make this sio event camelCase, consistent with others
    await sio.emit("user_list_update", connectedUsers) 


async def on_completed(mode: str):
    task_completion_timers[mode].stop()
    time_id = mode2expids[mode]
    # get session info for folder names
    session_name = f"{time_id}"
    session_log_dir = log_dir / session_name
    session_log_dir.mkdir(parents=True, exist_ok=True)
    

    comp_time = task_completion_timers[mode].elapsed

    #save interaction history for session
    usernames = interaction_recorders[mode].save_session(session_log_dir) 

    for username in usernames: 
        user_log_dir = log_dir / username / session_name
        sid = [sid for sid, name in sid2username.items() if name == username][0]
        userid = sid2userid[sid]
        compute_usermetrics(user_log_dir, userid, save = True) 
        interaction_recorders[mode].save_userinfo(user_log_dir, userid)

    compute_sessionmetrics(session_log_dir,info = comp_time,  save=True) 
    await _server_stop(mode, is_completed=True)


@sio.on("addUser")
async def add_user(sid, data):
    # NOTE: call this after "taskStartRequested" since the interaction recorder is reset at the start
    mode = modes[sid]
    interaction_recorders[mode].add_user(sid2userid[sid], data)
    return True


@sio.on("requestServerStart") # getting username here to use as key to find exp_id is not trivial. connected users doesnt show all users here yet.
async def server_start(sid):
    mode = modes[sid]
    env = envs[mode]
    assert not env.is_running
    
    mode2expids[mode] = datetime.now().strftime("%Y%m%d%H%M%S")

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
    username = sid2username[sid]
    res = await envs[mode].update_and_notify_command(
        command_label,
        agent_id,
        username,
        data["likelihoods"],
        data["interactionTime"],
    )
    
    if res["interactionTime"] is not None:  # TODO: recording only acceptable interactions
        res.pop("nextAcceptableCommands")  # delete unnecessary item
        interaction_recorders[mode].record(sid2userid[sid], res)
    
    print(f"Command {command_label} by {username} is sent to {agent_id}")

@sio.on("webrtc-offer-request")
async def webrtc_offer_request(sid, userinfo):
    pc = peer_connections[sid]
    mode = modes[sid]

    keys_to_remove = [key for key, value in sid2username.items() if value == userinfo["name"]]
    for key in keys_to_remove:
        sid2username.pop(key)

    sid2username[sid] = userinfo["name"]

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
    # Require within __main__ for rendering in parallel sub envs.
    mp.set_start_method("spawn")

    log_dir = app_dir / "logs"
    key_dir = app_dir / "../.keys"  # for HTTPS

    uvicorn.run(
        socket_app,
        host="0.0.0.0",
        port=8000,
        ssl_keyfile=str(key_dir / "server.key"),
        ssl_certfile=str(key_dir / "server.crt"),
    )
