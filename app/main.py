import asyncio
import base64
import json
from io import BytesIO
from typing import Dict, List

import gym
import robohive.envs.arms  # noqa: F401 # type: ignore
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


@app.get("/")
async def get(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "num_agents": num_agents})


@app.websocket("/browser")
async def websocket_endpoint_image(websocket: WebSocket):
    await websocket.accept()
    ws_clients["browser"] = websocket

    # run environment
    task = asyncio.create_task(env_process(websocket))

    try:
        while True:
            txt = await websocket.receive_text()
            print(f"/browser: received {txt}")

            data = json.loads(txt)
            if data["type"] in ["keyup", "keydown"]:
                update_command_ws(data)
    except WebSocketDisconnect:
        print("/browser: Client disconnected")
        task.cancel()  # env state is preserved since it's a global variable


@app.websocket("/pupil")
async def websocket_endpoint_input(websocket: WebSocket):
    await websocket.accept()
    ws_clients["pupil"] = websocket
    try:
        while True:
            txt = await websocket.receive_text()
            print(f"/pupil: received {txt}")
            await ws_clients["browser"].send_text(txt)  # send to browser
    except WebSocketDisconnect:
        print("/pupil: Client disconnected")


# TODO: also receive signals from BMI server through zmq


def update_command_ws(data):
    global command

    if data["type"] == "keydown":
        if data["key"] == "0":
            command[data["focusId"]] = 0
        elif data["key"] in ("1", "2", "3"):
            command[data["focusId"]] = 1


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
            await websocket.send_text(
                json.dumps({"type": "image", "data": img_str, "id": f"camera_{i}"})
            )

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
