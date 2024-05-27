import asyncio
import os
import platform
import subprocess

import gym
import numpy as np
import robohive_multi  # Makes the environments accessible # noqa: F401 # type: ignore
import socketio
from robohive_multi.motion_planner import MotionPlannerPolicy, gen_robot_names  # type: ignore

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

dt_step = 0.03


class EnvRunner:
    def __init__(
        self,
        env_id: str,
        sio: socketio.AsyncServer = None,
        on_completed=None,
        use_cancel_command: bool = False,
    ) -> None:
        self.is_running = False
        self._sio = sio

        # callbacks
        self.on_completed = on_completed

        self.env = gym.make(env_id)
        self.num_agents = self.env.nrobots
        self.a_dim_per_agent = self.env.action_space.shape[0] // self.num_agents

        # self.env.color_dict: {"100": 0, "010": 1, ...}
        # key digits correspond to "rgb", values correspond to the rgb index in Mujoco?
        self.command_colors = list(self.env.color_dict.keys())
        self.num_subtasks = len(self.command_colors)
        self.command_labels = [f"color{i + 1}" for i in range(len(self.command_colors))]  # TODO: more meaningful names?
        if use_cancel_command:
            # add cancel command
            self.command_colors.append("000")
            self.command_labels.append("cancel")

        # states
        self.command: list[str] = [""] * self.num_agents  # command from user
        self.prev_executed_command: list[str] = [""] * self.num_agents  # command at the previous action
        self.next_acceptable_commands: list[list[str]] = list(
            map(self._get_next_acceptable_commands, self.command)
        )  # next acceptable commands for each agent

        # init policies
        horizon = 2  # TODO
        self.policies = [MotionPlannerPolicy(self.env, *gen_robot_names(i), horizon) for i in range(self.num_agents)]

        # reset env for rendering
        self._reset_env()

    async def _notify(self, event, data=None):
        if self._sio is None:
            return
        await self._sio.emit(event, data)

    def _get_next_acceptable_commands(self, current_command):
        """Return next acceptable commands for the given command."""
        # Commands identical to the current one are unacceptable.
        if current_command == "":
            # If command is not set, all commands are acceptable
            return ["", *self.command_labels]
        elif current_command == "cancel":
            # If cancel command is set, no command is acceptable until cancel is done
            return []
        else:
            # If manipulation command is set, only cancel command is acceptable
            return ["cancel"]

    async def reset(self):
        # reset interface (EnvRunner) states
        await self._clear_commands()
        self.prev_executed_command = [""] * self.num_agents

        # reset env
        obs = self._reset_env()
        return obs

    def _reset_env(self):
        obs = self.env.reset()
        # reset policies
        # TODO: move this to MotionPlannerPolicy to reset internally?
        for policy in self.policies:
            policy.reset(self.env)
            policy.subtask_target_obj_idxs = []
            policy.done_obj_idxs = []
            policy.done_subtasks = []
        return obs

    async def _clear_commands(self):
        # TODO: parallelize
        for idx_agent in range(self.num_agents):
            # TODO: use something like force=True or the "cancel" command
            self.next_acceptable_commands[idx_agent].append("")
            await self.update_and_notify_command("", idx_agent)

    def start(self):
        self.is_running = True
        obs = self._reset_env()
        self.task = asyncio.create_task(self._run(obs))
        print("env loop started")

    async def stop(self):
        self.is_running = False
        # cancel the task
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            print("env loop stopped")
        # reset
        await self.reset()

    async def _run(self, init_obs):
        env = self.env
        obs = init_obs

        while self.is_running:
            action, subtask_dones = self._get_policy_action(obs, self.command, norm=False)

            # check if subtask is done
            if any(subtask_dones):
                for idx_agent, done in enumerate(subtask_dones):
                    if not done:
                        continue

                    policy = self.policies[idx_agent]
                    policy.reset(self.env)  # TODO: is this correct?
                    await self._notify("subtaskDone", {"agentId": idx_agent, "subtask": self.command[idx_agent]})
                    # reset command
                    self.next_acceptable_commands[idx_agent].append("")  # TODO
                    await self.update_and_notify_command("", idx_agent)

            # check if all tasks are done
            # TODO: sync with policy.done?
            if all([len(policy.done_subtasks) == self.num_subtasks for policy in self.policies]):
                if self.on_completed is not None:
                    self.on_completed()
                for policy in self.policies:
                    policy.done_subtasks = []  # TODO: not intuitive

            obs, _, done, _ = env.step(action)

            await asyncio.sleep(dt_step)

    def _get_policy_action(self, obs, command, norm=True):
        actions = []
        subtask_dones = []
        for idx_policy, policy in enumerate(self.policies):
            c = command[idx_policy]
            if c == "":
                # command not set
                a = self._get_base_action()
                subtask_done = False
            elif c == "cancel":
                # cancel command
                policy.reset(self.env)  # TODO: is this correct?
                a = self._get_base_action()
                # TODO: check if robot posture has been reset
                subtask_done = True
            else:
                # subtask command
                if self.prev_executed_command[idx_policy] != c:
                    # command changed since the previous action
                    self.prev_executed_command[idx_policy] = c

                    # from command label to rgb index in Mujoco
                    # TODO: make a dict for this?
                    target_color_idx = self.env.color_dict[self.command_colors[self.command_labels.index(c)]]

                    # find target object indices
                    policy.subtask_target_obj_idxs = [
                        idx_obj
                        for idx_obj, (_, target_name) in enumerate(policy.obj_target_pairs)
                        if target_name[-1] == str(target_color_idx + 1)
                        # target_name is in the form "drop_target{robot_idx}_{color_idx + 1}"
                    ]

                if len(policy.subtask_target_obj_idxs) == 0:
                    # invalid command
                    policy.reset(self.env)  # TODO: is this correct?
                    a = self._get_base_action()
                    subtask_done = True
                else:
                    policy.current_target_indx = policy.subtask_target_obj_idxs[0]
                    # TODO: initial current_target_indx is 0, but -1 or None is better?
                    # TODO: use policy.get_action, after modifying it not to reset internally
                    box_name, target_name = policy.obj_target_pairs[policy.current_target_indx]
                    policy.planner.box_name = box_name
                    policy.planner.target_name = target_name

                    a = policy.planner.get_action()
                    if policy.planner.done:
                        # manipulation of the target object is done
                        done_obj_idx = policy.subtask_target_obj_idxs.pop(0)
                        policy.done_obj_idxs.append(done_obj_idx)
                        subtask_done = len(policy.subtask_target_obj_idxs) == 0
                    else:
                        subtask_done = False

            if subtask_done and c not in ["", "cancel"]:
                # command and subtask are 1:1 relation for now
                policy.done_subtasks.append(c)

            actions.append(a)
            subtask_dones.append(subtask_done)

        action = np.concatenate(actions)
        if norm:
            action_indices = np.concatenate([policy.planner.dof_indices for policy in self.policies])
            action = self.policies[0].norm_act(action[action_indices])

        return action, subtask_dones

    def _get_base_action(self):
        # TODO: fix and use env.get_base_action()
        low = self.env.action_space.low[: self.a_dim_per_agent]
        high = self.env.action_space.high[: self.a_dim_per_agent]
        return low + (high - low) / 2  # (a_dim_per_agent, )

    async def update_and_notify_command(self, command, agent_id, likelihoods=None, interaction_time=None):
        # self.command should be updated only by this method
        # likelihoods and interaction_time would be None when called internally

        # check if the command is valid
        is_now_acceptable = command in self.next_acceptable_commands[agent_id]
        has_subtask_not_done = command not in self.policies[agent_id].done_subtasks
        is_valid = is_now_acceptable and has_subtask_not_done

        next_acceptable_commands = self._get_next_acceptable_commands(command)

        # update command only if it is valid
        if is_valid:
            self.command[agent_id] = command
            self.next_acceptable_commands[agent_id] = next_acceptable_commands

        # remove interaction time if the command is not acceptable
        if not is_now_acceptable:
            interaction_time = None

        data = {
            "agentId": agent_id,
            "command": command,
            "nextAcceptableCommands": next_acceptable_commands,
            "isNowAcceptable": is_now_acceptable,
            "hasSubtaskNotDone": has_subtask_not_done,
            "likelihoods": likelihoods,
            "interactionTime": interaction_time,
        }

        # send the command info to update the charts and debug log in the frontend
        await self._notify("command", data)

        return data
