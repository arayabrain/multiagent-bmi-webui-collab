import asyncio
import multiprocessing as mp
import os
import platform
import subprocess
import time

import gym
import numpy as np
import robohive_multi  # Makes the environments accessible # noqa: F401 # type: ignore
from robohive_multi.motion_planner import MotionPlannerPolicy, gen_robot_names
from app.async_vector_env import AsyncVectorEnv

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
        num_agents: int,
        notify_fn=None,  # function to send message to all clients in the same mode
        on_completed_fn=None,  # function to call when all subtasks are done
        use_cancel_command: bool = False,
    ) -> None:
        self.is_running = False

        # callbacks
        self.notify_fn = notify_fn
        self.on_completed_fn = on_completed_fn

        if num_agents < 1:
            self.env = gym.make(env_id)
        else:
            # NOTE: builds sub_envs based on pattern:
            # "FrankaProcedural{max_agents_per_env}Robots4Col-v0" * num_agents
            self.env = MultiRobotSubEnvWrapper(num_agents=num_agents, max_agents_per_env=1)

        self.num_agents = num_agents
        if isinstance(self.env, MultiRobotSubEnvWrapper):
            self.a_dim_per_agent = self.env.sub_envs.single_action_space.shape[0] // self.env.max_agents_per_env
        else:
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
        if isinstance(self.env, MultiRobotSubEnvWrapper):
            # Motion Planner Policies are setup within the env itself, parallelization
            self.env.setup_motion_planner_policies(horizon=horizon)
            self.policies_done_subtasks = [[] for i in range(self.num_agents)] # Placeholder
        else:
            self.policies = [MotionPlannerPolicy(self.env, *gen_robot_names(i), horizon) for i in range(self.num_agents)]

        # reset env for rendering
        self._reset_env()

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
        if isinstance(self.env, MultiRobotSubEnvWrapper):
            # Makes the policies within each parallel env reset the robot they in charge of
            self.env.policy_reset_env()
        else:
            # TODO: test even with single-robot mode, make AsyncVectorEnv default
            # then NUKE everything below.
            for idx_policy, policy in enumerate(self.policies):
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

                    sub_env_idx = idx_agent // self.sub_envs.max_agents_per_env
                    sub_env_robot_idx = idx_agent % self.sub_envs.max_agents_per_env
                    # For an agent_idx, access the corresponding (parallel) sub_env,
                    # then use the policy in charge of `sub_env_robot_idx` to reset that
                    # specific robot
                    # TODO: need to test in 4 envs * 4 robots for e.g., make sure
                    # we get the desired behavior, not just the first robot being reset.
                    self.env.policy_reset_env_single(sub_env_idx, sub_env_robot_idx)

                    # Legacy below, nuke
                    # policy = self.policies[idx_agent]
                    # if isinstance(self.env, MultiRobotSubEnvWrapper):
                    #     sub_env_idx = idx_agent // self.env.max_agents_per_env
                    #     policy.reset(self.env.sub_envs[sub_env_idx])
                    # else:
                    #     policy.reset(self.env)  # TODO: is this correct?
                    # end legacy
                    await self.notify_fn("subtaskDone", {"agentId": idx_agent, "subtask": self.command[idx_agent]})
                    # reset command
                    self.next_acceptable_commands[idx_agent].append("")  # TODO
                    await self.update_and_notify_command("", idx_agent)

            # check if all tasks are done
            # TODO: sync with policy.done?
            # TODO: custom async+wait to check that all policies done_subtasks ?
            self.policies_done_subtasks = env.get_policy_done_subtasks()
            if all([len(pol_done_subtasks) == self.num_subtasks for pol_done_subtasks in self.policies_done_subtasks]):
                if self.on_completed_fn is not None:
                    self.on_completed_fn()
                
                # for idx_agent, policy in self.policies:
                for idx_agent in range(self.num_agents):
                    sub_env_idx = idx_agent // self.sub_envs.max_agents_per_env
                    sub_env_robot_idx = idx_agent % self.sub_envs.max_agents_per_env
                    self.sub_envs.policy_reset_done_subtasks(sub_env_idx, sub_env_robot_idx)
                    # Legacy; TODO: nuke later once confirmed working
                    # policy.done_subtasks = []  # TODO: not intuitive

            obs, _, done, _ = env.step(action)

            await asyncio.sleep(dt_step)

    def _get_policy_action(self, obs, command, norm=True):
        if isinstance(self.env, MultiRobotSubEnvWrapper):
            # motion planner computes actions async. in parallel sub envs
            # then cummulated here for the step() call, and subtask tracking
            action, subtask_dones = self.env.sub_envs.get_policy_action(obs, command, norm)
            return action, subtask_dones
        else:
            raise NotImplementedError("Getting action for non MultiRobotSubEnvWrapper not support now")

    async def update_and_notify_command(self, command, agent_id, likelihoods=None, interaction_time=None):
        # self.command should be updated only by this method
        # likelihoods and interaction_time would be None when called internally

        # check if the command is valid
        is_now_acceptable = command in self.next_acceptable_commands[agent_id]
        has_subtask_not_done = command not in self.policies_done_subtasks[agent_id]
        # Legacy; TODO: nuke later
        # has_subtask_not_done = command not in self.policies[agent_id].done_subtasks
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
        await self.notify_fn("command", data)

        return data


# Wrapper class to breakdown envs with 4+ agents
# into multiple sub_envs to mitigate slow simulator speed
class MultiRobotSubEnvWrapper():
    def __init__(self, num_agents, max_agents_per_env=4):
        # This class all the sub_envs have the same number of robots !
        assert num_agents % max_agents_per_env == 0, \
            f"Cannot break down env with {num_agents} into exact sub envs with {max_agents_per_env}."
        self.max_agents_per_env = max_agents_per_env
        self.n_sub_envs = num_agents // max_agents_per_env

        # TODO: Needs to be adjusted to support other pattern of envs later on.
        sub_env_name = f"FrankaProcedural{max_agents_per_env}Robots4Col-v0"

        # AsyncVectorEnv wrapper where each env is run is a sub process, relieving the main one
        self.sub_envs = AsyncVectorEnv([lambda: gym.make(sub_env_name) for _ in range(self.n_sub_envs)], shared_memory=False)

        # Attribute for compatibility with EnvRunner
        self.action_space = self.sub_envs.single_action_space
        # TODO: unharden
        # self.color_dict = self.sub_envs[0].color_dict
        self.color_dict = {
            "100": 0,
            "010": 1,
            "001": 2,
            "110": 3
        }

    def get_visuals(self):
        # Accumulate and returns the visuals for stream_manager mainly
        visual_list = self.sub_envs.get_visuals()

        visuals = {}
        # visual_list = [sub_env.get_visuals() for sub_env in self.sub_envs]

        sub_env_agent_idx = 0 # track current agent idx from POV of desired total num_agents.
        for sub_env_visual_dict in visual_list:
            for k, v in sub_env_visual_dict.items():
                # TODO: generalize to work with patterns other than rgb:franka<i>_front_cam:256x256x2d ?
                if not k.startswith("rgb:franka"):
                    continue

                # TODO: add support in stream manager for more flex
                resolution = k.split(":")[2]
                visuals[f"rgb:franka{sub_env_agent_idx}_front_cam:{resolution}:2d"] = v
                sub_env_agent_idx += 1
        
        return visuals
    
    def step(self, action):
        # step over all envs in the AsyncVectorEnv wrapper
        return self.sub_envs.step(action)

    def reset(self):
        return self.sub_envs.reset()

    # AsyncVectorEnv does not use this helper fn, but
    # leaving for ref. as it will be useful for
    # sub envs with multiple robots within later.
    def status_led_setter(self, idx_policy, fn_name):
        sub_env_idx = idx_policy // self.max_agents_per_env
        sub_env_agent_idx = idx_policy % self.max_agents_per_env
        getattr(self.sub_envs[sub_env_idx], fn_name)(sub_env_agent_idx)

    def status_led_off(self, sub_env_idx):
        # AsyncVectorEnv variant
        self.sub_envs.set_status_led_off(sub_env_idx)
    
    def status_led_on(self, sub_env_idx):
        # AsyncVectorEnv variant
        self.sub_envs.set_status_led_on(sub_env_idx)


    # Setup Motion Planner Policies within each parallel env
    def setup_motion_planner_policies(self, horizon):
        return self.sub_envs.setup_motion_planner_policies(horizon)
    

    # Make the policies within parallel envs reset the position
    # of the robot hey are in charge of
    def policy_reset_env(self):
        return self.sub_envs.policy_reset_env()

    # Get the done_subtasks state of each policy in the parallel envs
    def get_policy_done_subtasks(self):
        return self.sub_envs.get_policy_done_subtasks()


# If run as main, tests basic AsyncVectorEnv wrapper around robohive-multi envs.
if __name__ == "__main__":
    # Require within __main__ for visual obs rendering with multiprocessing
    mp.set_start_method("spawn")
    N_ROBOTS = 16

    envs = AsyncVectorEnv([lambda: gym.make("FrankaProcedural1Robots4Col-v0")
                            for _ in range(N_ROBOTS)])

    # Testing LED on / off pure async toggle fns
    for i in range(N_ROBOTS):
        envs.set_status_led_off(i)
        envs.set_status_led_on(i)
    
    while True:
        visuals = envs.get_visuals()
        time.sleep(1 / 60)

    # print(visuals[0].keys())
    pass
