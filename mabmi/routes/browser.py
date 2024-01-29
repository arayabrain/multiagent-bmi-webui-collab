import asyncio
from typing import List

import gym
import numpy as np
import robohive.envs.arms  # noqa: F401 # type: ignore
from aiortc import VideoStreamTrack
from av import VideoFrame
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from mabmi.app.app_state import AppState
from mabmi.utils.webrtc import createPeerConnection, handle_answer, handle_candidate, handle_offer_request

router = APIRouter()


@router.websocket("/browser")
async def ws_browser(websocket: WebSocket):
    """Websocket endpoint for browser client

    Args:
        websocket (WebSocket): websocket connection from browser
    """
    await websocket.accept()
    print("/browser: Client connected")

    state: AppState = websocket.app.state
    state.ws_connections["browser"] = websocket

    # run environment
    env_proc = EnvProcess(state)
    env_proc.start()

    try:
        while True:
            data = await websocket.receive_json()

            if data["type"] in ("keyup", "keydown"):
                print(f"/browser: received {data}")
                state.update_command(data)
            elif data["type"] == "focus":
                print(f"/browser: received {data}")
                state.focus = data["focusId"]

            elif data["type"] == "webrtc-offer-request":
                pc = createPeerConnection(websocket)
                state.peer_connections["browser"] = pc

                # add stream tracks
                for i in range(state.num_agents):
                    track = state.relay.subscribe(ImageStreamTrack(env_proc, i))
                    pc.addTransceiver(track, direction="sendonly")
                    print(f"Track {track.id} added to peer connection")

                await handle_offer_request(pc, websocket)
            elif data["type"] == "webrtc-answer":
                await handle_answer(pc, data)
            elif data["type"] == "webrtc-ice":
                await handle_candidate(pc, data)

    except WebSocketDisconnect:
        print("/browser: Client disconnected")
        env_proc.stop()
        pc = state.peer_connections.pop("browser", None)
        if pc:
            await pc.close()


class EnvProcess:
    def __init__(self, state: AppState):
        self.num_agents = state.num_agents

        self.env = gym.make("FrankaReachFixedMulti-v0")
        self.a_dim_per_agent = self.env.action_space.shape[0] // self.num_agents

        self.frames: List[np.ndarray | None] = [None] * self.num_agents
        self.frame_update_cond = asyncio.Condition()
        self.command = state.command  # updated globally

    def start(self):
        self.task = asyncio.create_task(self._env_process())
        # TODO: separate thread?

    def stop(self):
        self.task.cancel()

    async def _env_process(self):
        print("env_process started")
        env = self.env

        # init
        obs = env.reset()

        while True:
            action = self._get_action(obs, self.command)
            obs, _, done, _ = env.step(action)
            visuals = env.get_visuals()

            async with self.frame_update_cond:
                for i in range(self.num_agents):
                    self.frames[i] = visuals[f"rgb:franka{i}_front_cam:256x256:1d"].reshape((256, 256, 3))
                self.frame_update_cond.notify_all()

            if done:
                env.reset()

            await asyncio.sleep(0.03)

    def _get_action(self, obs, command):
        # TODO: use policy

        action = self.env.action_space.sample()
        # zero actions for agents with command 0
        for i in range(self.num_agents):
            if command[i] == 0:
                action[i * self.a_dim_per_agent : (i + 1) * self.a_dim_per_agent] = 0

        return action


class ImageStreamTrack(VideoStreamTrack):
    def __init__(self, env_proc, camera_idx: int):
        super().__init__()
        self.camera_idx = camera_idx

        # references to variables in EnvProcess
        self.cond = env_proc.frame_update_cond
        self.frames = env_proc.frames

    async def recv(self):
        global frames

        async with self.cond:
            await self.cond.wait()
            frame = self.frames[self.camera_idx]

        img = frame
        frame = VideoFrame.from_ndarray(img, format="rgb24")
        pts, time_base = await self.next_timestamp()
        frame.pts = pts
        frame.time_base = time_base

        return frame
