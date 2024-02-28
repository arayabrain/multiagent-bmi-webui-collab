import asyncio
import os

import custom_robohive_design.env_init  # noqa: F401 # type: ignore
import gym
import numpy as np
import robohive  # noqa: F401 # type: ignore
from aiortc import VideoStreamTrack
from av import VideoFrame
from custom_robohive_design.multiagent_motion_planner_policy import (  # noqa: F401 # type: ignore
    MotionPlannerPolicy,
    gen_robot_names,
    simulate_action,
)

from app.app_state import AppState

os.environ["MUJOCO_GL"] = "egl"  # for headless rendering


# env_id = "FrankaReachFixedMulti-v0"

env_id = "FrankaPickPlaceMulti-v0"
class_colors = [
    "rgba(30, 25, 255, 0.3)",  # blue
    "rgba(64, 212, 0, 0.3)",  # green
    "rgba(255, 24, 0, 0.3)",  # red
]


class EnvRunner:
    def __init__(self, state: AppState):
        self.num_agents = state.num_agents
        self.is_running = False

        self.env = gym.make(env_id)
        self.a_dim_per_agent = self.env.action_space.shape[0] // self.num_agents
        self.class_colors = class_colors

        self.frames: list[np.ndarray | None] = [None] * self.num_agents
        self.frame_update_cond = asyncio.Condition()
        self.command = state.command  # updated globally

        # init policies
        # horizon = 10
        horizon = 2  # TODO
        self.policies = [MotionPlannerPolicy(self.env, *gen_robot_names(i), horizon) for i in range(self.num_agents)]

    def _reset(self):
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
                if c != policy.current_target_indx:
                    # new target
                    policy.reset(self.env)
                    policy.current_target_indx = c
                a = policy.get_action()
            action.append(a)

        action = np.concatenate(action)
        if norm:
            action_indices = np.concatenate([policy.planner.dof_indices for policy in self.policies])
            action = self.policies[0].norm_act(action[action_indices])
        return action


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
    state = AppState()
    runner = EnvRunner(state)
    runner.is_running = True
    asyncio.run(runner._run())
