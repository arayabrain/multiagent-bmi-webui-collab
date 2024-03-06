import asyncio
import os
import platform

import custom_robohive_design.env_init  # noqa: F401 # type: ignore
import gym
import numpy as np
import robohive  # noqa: F401 # type: ignore
import socketio
from aiortc import VideoStreamTrack
from av import VideoFrame
from custom_robohive_design.multiagent_motion_planner_policy import (  # noqa: F401 # type: ignore
    MotionPlannerPolicy,
    gen_robot_names,
    simulate_action,
)

if platform.system() == "Linux":
    os.environ["MUJOCO_GL"] = "egl"  # for headless rendering


class EnvRunner:
    def __init__(self, env_id: str, sio: socketio.AsyncServer = None) -> None:
        self.is_running = False

        self.env = gym.make(env_id)
        self.num_agents = self.env.nrobots
        self.a_dim_per_agent = self.env.action_space.shape[0] // self.num_agents
        self.class2color = {v + 1: k for k, v in self.env.color_dict.items()}
        # {1: "001", 2: "010", ...}; digits correspond to rgb

        self.sio = sio

        # states
        self.command: list[int] = [0] * self.num_agents  # command from user
        self.is_action_running: list[bool] = [False] * self.num_agents
        self.focus_id: int | None = None  # user focus

        # placeholders for frames to stream
        self.frames: list[np.ndarray | None] = [None] * self.num_agents
        self.frame_update_cond = asyncio.Condition()

        # init policies
        # horizon = 10
        horizon = 2  # TODO
        self.policies = [MotionPlannerPolicy(self.env, *gen_robot_names(i), horizon) for i in range(self.num_agents)]

    def _reset(self):
        self.command = [0] * self.num_agents
        self.is_action_running = [False] * self.num_agents
        # we don't reset focus_id

        obs = self.env.reset()
        for policy in self.policies:
            policy.reset(self.env)
        return obs

    def start(self):
        self.is_running = True
        self.task = asyncio.create_task(self._run())

    async def stop(self):
        self.is_running = False
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            print("env_process cancelled")

    async def _run(self):
        print("env_process started")
        env = self.env
        obs = self._reset()

        while self.is_running:
            # action = self._get_random_action(obs, self.command)

            # action = self._get_policy_action(obs, self.command)
            # obs, _, done, _ = env.step(action)

            action = self._get_policy_action(obs, self.command, norm=False)
            action_indices = np.concatenate([policy.planner.dof_indices for policy in self.policies])
            simulate_action(env.sim, action[np.newaxis, :], action_indices, render=False)
            done = False

            visuals = env.get_visuals()

            async with self.frame_update_cond:
                for i in range(self.num_agents):
                    self.frames[i] = visuals[f"rgb:franka{i}_front_cam:256x256:1d"].reshape((256, 256, 3))
                self.frame_update_cond.notify_all()

            if done or all([policy.done for policy in self.policies]):
                obs = self._reset()

            await asyncio.sleep(0.03)

    def _get_random_action(self, obs, command):
        action = self.env.action_space.sample()
        # zero actions for agents with command 0
        for i in range(self.num_agents):
            if command[i] == 0:
                action[i * self.a_dim_per_agent : (i + 1) * self.a_dim_per_agent] = 0

        return action

    def _get_policy_action(self, obs, command, norm=True):
        # TODO: set command for each policy
        # command: 0, 1, 2, 3 correspond to no action and three colors
        action = []
        for c, policy in zip(command, self.policies):
            if c == 0:
                a = np.zeros(self.a_dim_per_agent)
            else:
                target_idx = c - 1
                # FIXME: there are only two targets in the env for now
                if target_idx not in [0, 1]:
                    a = np.zeros(self.a_dim_per_agent)
                if target_idx != policy.current_target_indx:
                    # new target
                    policy.reset(self.env)
                    policy.current_target_indx = target_idx
                a = policy.get_action()
            action.append(a)

        action = np.concatenate(action)
        if norm:
            action_indices = np.concatenate([policy.planner.dof_indices for policy in self.policies])
            action = self.policies[0].norm_act(action[action_indices])
        return action

    async def update_command(self, event, data):
        if self.focus_id is None:
            return
        if self.is_action_running[self.focus_id]:
            # ignore commands if action is running
            return

        command = None
        if event == "eeg":
            # assume data is a command
            command = data
        elif event == "keydown":
            # assume data is a key
            if data in [str(i) for i in range(len(self.class2color))]:
                command = int(data)

        if command is not None:
            # update command
            self.command[self.focus_id] = command
            # update is_action_running
            if command > 0:
                self.is_action_running[self.focus_id] = True

            await self.notify_command()

    async def notify_command(self, sid=None):
        if self.sio is not None:
            await self.sio.emit("command", self.command, to=sid)

    # TODO: update self.is_action_running if action is done


class ImageStreamTrack(VideoStreamTrack):
    def __init__(self, env: EnvRunner, camera_idx: int):
        super().__init__()
        self.camera_idx = camera_idx

        # references to variables in EnvProcess
        self.cond = env.frame_update_cond
        self.frames = env.frames

    async def recv(self):
        async with self.cond:
            await self.cond.wait()
            frame = self.frames[self.camera_idx]

        frame = VideoFrame.from_ndarray(frame, format="rgb24")
        pts, time_base = await self.next_timestamp()
        frame.pts = pts
        frame.time_base = time_base

        return frame


if __name__ == "__main__":
    runner = EnvRunner("FrankaPickPlaceMulti4-v0")
    runner.is_running = True
    asyncio.run(runner._run())
