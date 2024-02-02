import asyncio
from typing import List

import gym
import numpy as np
import robohive.envs.arms  # noqa: F401 # type: ignore
from app_state import AppState


class EnvRunner:
    def __init__(self, state: AppState):
        self.num_agents = state.num_agents

        self.env = gym.make("FrankaReachFixedMulti-v0")
        self.a_dim_per_agent = self.env.action_space.shape[0] // self.num_agents

        self.frames: List[np.ndarray | None] = [None] * self.num_agents
        self.frame_update_cond = asyncio.Condition()
        self.command = state.command  # updated globally

    def start(self):
        self.task = asyncio.create_task(self._run())
        # TODO: separate thread?

    async def stop(self):
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            pass

    async def _run(self):
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
