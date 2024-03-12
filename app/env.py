import asyncio
import os
import platform
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

# check if display is available on Linux
if platform.system() == "Linux":
    print("Checking display...")
    try:
        subprocess.run(["xdpyinfo"], check=True, timeout=1, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("Display is available")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        print("Display is not available, using egl rendering")
        os.environ["MUJOCO_GL"] = "egl"

# NOTE: rendering is slow without GPU


class EnvRunner:
    def __init__(self, env_id: str, sio: socketio.AsyncServer = None) -> None:
        self.is_running = False

        self.env = gym.make(env_id)
        self.num_agents = self.env.nrobots
        self.a_dim_per_agent = self.env.action_space.shape[0] // self.num_agents

        self.num_classes = len(self.class2color)
        self.command_keys = [str(i) for i in range(self.num_classes)]  # ["0", "1", ...]

        self.sio = sio

        # states
        command, prev_action_command, acceptable_commands, focus_id = self._get_init_states()
        self.command: list[int | None] = command  # command from user
        self.prev_action_command: list[int | None] = prev_action_command  # command at the previous action
        self.next_acceptable_commands: list[list[int | None]] = (
            acceptable_commands  # next acceptable commands for each agent
        )
        self.focus_id: int | None = focus_id  # user focus

        # placeholders for frames to stream
        self.frames: list[np.ndarray | None] = [None] * self.num_agents
        self.frame_update_cond = asyncio.Condition()

        # init policies
        # horizon = 10
        horizon = 2  # TODO
        self.policies = [MotionPlannerPolicy(self.env, *gen_robot_names(i), horizon) for i in range(self.num_agents)]
        for policy in self.policies:
            policy.target_obj_idxs = []
            # TODO: move this to MotionPlannerPolicy?

    @property
    def class2color(self):
        # {0: "000", 1: "001", ...}
        # digits correspond to rgb
        dic = {v + 1: k for k, v in self.env.color_dict.items()}
        dic[0] = "000"  # cancel action
        return dic

    def _get_init_states(self):
        command = [None] * self.num_agents
        prev_action_command = [None] * self.num_agents
        next_acceptable_commands = list(map(self._get_next_acceptable_commands, command))
        focus_id = None
        return command, prev_action_command, next_acceptable_commands, focus_id

    def _get_next_acceptable_commands(self, current_command):
        """Return next acceptable commands for the given command."""
        # Commands identical to the current one are unacceptable.
        if current_command is None:
            # If command is not set, all commands are acceptable
            return list(range(self.num_classes))
        elif current_command == 0:
            # If cancel command is set, no command is acceptable until cancel is done
            return []
        else:
            # If manipulation command is set, only cancel command is acceptable
            return [0]

    def _reset(self):
        self.command, self.prev_action_command, self.next_acceptable_commands, _ = self._get_init_states()
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
            action, subtask_dones = self._get_policy_action(obs, self.command, norm=False)

            # reset policy if subtask is done
            if any(subtask_dones):
                for i, done in enumerate(subtask_dones):
                    if done:
                        self.policies[i].reset(self.env)
                        await self._update_and_notify_command(None, i)

            # obs, _, done, _ = env.step(action)

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
        # TODO: remove this?
        action = self.env.action_space.sample()
        # zero actions for agents with command 0
        for i in range(self.num_agents):
            if command[i] == 0:
                action[i * self.a_dim_per_agent : (i + 1) * self.a_dim_per_agent] = 0

        return action

    def _get_policy_action(self, obs, command, norm=True):
        actions = []
        subtask_dones = []
        for idx_policy, policy in enumerate(self.policies):
            c = command[idx_policy]
            if c is None:
                # command not set
                # TODO: is zero the initial state?
                a = np.zeros(self.a_dim_per_agent)
                subtask_done = False
            elif c == 0:
                # cancel command
                policy.reset(self.env)
                a = np.zeros(self.a_dim_per_agent)
                # TODO: check if robot posture has been reset
                subtask_done = True
            else:
                # manipulation command
                if self.prev_action_command[idx_policy] != c:
                    # command changed since the previous action
                    self.prev_action_command[idx_policy] = c

                    target_color_idx = c - 1  # -1 because 0 is cancel command

                    # find target object indices
                    target_obj_idxs = []
                    for idx_obj, (_, target_name) in enumerate(policy.obj_target_pairs):
                        # target_name: "drop_target{robot_idx}_{color_idx + 1}"
                        if target_name[-1] == str(target_color_idx + 1):
                            target_obj_idxs.append(idx_obj)

                    # update target object indices
                    assert not np.array_equal(target_obj_idxs, policy.target_obj_idxs)  # since command changed
                    policy.target_obj_idxs = target_obj_idxs

                if len(policy.target_obj_idxs) == 0:
                    # invalid command
                    policy.reset(self.env)
                    a = np.zeros(self.a_dim_per_agent)
                    subtask_done = True
                else:
                    policy.current_target_indx = policy.target_obj_idxs[0]
                    # TODO: initial current_target_indx is 0, but -1 or None is better?
                    # TODO: use policy.get_action, after modifying it not to reset internally
                    box_name, target_name = policy.obj_target_pairs[policy.current_target_indx]
                    policy.planner.box_name = box_name
                    policy.planner.target_name = target_name

                    a = policy.planner.get_action()
                    if policy.planner.done:
                        # manipulation of the target object is done
                        policy.target_obj_idxs.pop(0)
                        subtask_done = len(policy.target_obj_idxs) == 0
                    else:
                        subtask_done = False

            actions.append(a)
            subtask_dones.append(subtask_done)

        action = np.concatenate(actions)
        if norm:
            action_indices = np.concatenate([policy.planner.dof_indices for policy in self.policies])
            action = self.policies[0].norm_act(action[action_indices])

        return action, subtask_dones

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

        if command in self.next_acceptable_commands[self.focus_id]:
            await self._update_and_notify_command(command, self.focus_id)

    async def _update_and_notify_command(self, command, agent_id):
        # self.command should be updated only by this method
        self.command[agent_id] = command
        self.next_acceptable_commands[agent_id] = self._get_next_acceptable_commands(command)
        await self.sio.emit(
            "command",
            {
                "agentId": agent_id,
                "command": self.command[agent_id],
                "nextAcceptableCommands": self.next_acceptable_commands[agent_id],
            },
        )

    async def notify_commands(self, agent_ids: list[int], sid=None):
        # notify client of the command of the specified agents
        # separate this method to be called from connect event
        if self.sio is None:
            print("Socket is not set")
            return

        await asyncio.gather(
            *[
                self.sio.emit(
                    "command",
                    {
                        "agentId": agent_id,
                        "command": self.command[agent_id],
                        "nextAcceptableCommands": self.next_acceptable_commands[agent_id],
                    },
                    to=sid,
                )
                for agent_id in agent_ids
            ]
        )


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
