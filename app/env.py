import asyncio
import os
import subprocess

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

# check if display is available
print("Checking display...")
try:
    subprocess.check_call(["xdpyinfo"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("Display is available")
except subprocess.CalledProcessError:
    print("Display is not available, using egl rendering")
    os.environ["MUJOCO_GL"] = "egl"


class EnvRunner:
    def __init__(self, env_id: str, sio: socketio.AsyncServer = None) -> None:
        self.is_running = False

        self.env = gym.make(env_id)
        self.num_agents = self.env.nrobots
        self.a_dim_per_agent = self.env.action_space.shape[0] // self.num_agents
        self.command_keys = [str(i) for i in range(len(self.class2color))]  # ["0", "1", ...]

        self.sio = sio

        # states
        self.command: list[int | None] = [None] * self.num_agents  # command from user
        self.focus_id: int | None = None  # user focus

        # placeholders for frames to stream
        self.frames: list[np.ndarray | None] = [None] * self.num_agents
        self.frame_update_cond = asyncio.Condition()

        # init policies
        # horizon = 10
        horizon = 2  # TODO
        self.policies = [MotionPlannerPolicy(self.env, *gen_robot_names(i), horizon) for i in range(self.num_agents)]

    @property
    def class2color(self):
        # {0: "000", 1: "001", ...}
        # digits correspond to rgb
        dic = {v + 1: k for k, v in self.env.color_dict.items()}
        dic[0] = "000"  # cancel action
        return dic

    def _reset(self):
        self.command = [None] * self.num_agents  # command from user
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

            # action = self._get_policy_action(obs, self.command, norm=False)

            action, dones = self._get_policy_action(obs, self.command, norm=False)
            # reset command to None if policy is done
            if any(dones):
                for i, done in enumerate(dones):
                    if done:
                        self.command[i] = None
                await self.notify_command()

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
        actions = []
        dones = []
        for c, policy in zip(command, self.policies):
            if c is None:
                # command not set
                a = np.zeros(self.a_dim_per_agent)
                done = False
            elif c == 0:
                # cancel command
                policy.reset(self.env)
                # TODO: Target's red cube don't go away
                a = np.zeros(self.a_dim_per_agent)
                done = True
            elif c >= 3:
                # FIXME: ignore command because there are only two targets in the env for now
                policy.reset(self.env)
                a = np.zeros(self.a_dim_per_agent)
                done = True
            else:
                # manipulation command
                target_idx = c - 1
                if target_idx != policy.current_target_indx:
                    # new target
                    policy.reset(self.env)
                    policy.current_target_indx = target_idx
                a = policy.get_action()
                done = policy.done
            actions.append(a)
            dones.append(done)

        action = np.concatenate(actions)
        if norm:
            action_indices = np.concatenate([policy.planner.dof_indices for policy in self.policies])
            action = self.policies[0].norm_act(action[action_indices])

        return action, dones

    async def update_command(self, event, data):
        if self.focus_id is None:
            return

        # convert data to command
        command = None
        if event == "eeg":
            # assume data is a command
            command = data
        elif event == "keydown":
            # assume data is a key
            if data in self.command_keys:
                command = int(data)

        is_running_action = self.command[self.focus_id] is not None  # include cancel in action
        is_starting_action = not is_running_action and command is not None
        is_canceling_action = is_running_action and command == 0
        # TODO: what if current and new action are both cancel?
        if is_starting_action or is_canceling_action:
            # update command
            print(f"update_command: {event} {data}")
            self.command[self.focus_id] = command
            await self.notify_command()

    async def notify_command(self, sid=None):
        # separate this method to be called from connect event
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
