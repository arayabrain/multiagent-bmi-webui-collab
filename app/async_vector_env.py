# Based on OpenAI Gym's AsyncVectorEnv: https://github.com/openai/gym/blob/0.13.0/gym/vector/async_vector_env.py

import numpy as np
import multiprocessing as mp
import time
import sys
from enum import Enum
from copy import deepcopy

from gym import logger
from gym.vector.vector_env import VectorEnv
from gym.error import (AlreadyPendingCallError, NoAsyncCallError,
                       ClosedEnvironmentError)
from gym.vector.utils import (create_shared_memory, create_empty_array,
                              write_to_shared_memory, read_from_shared_memory,
                              concatenate, CloudpickleWrapper, clear_mpi_env_vars)

__all__ = ['AsyncVectorEnv']


class AsyncState(Enum):
    DEFAULT = 'default'
    WAITING_RESET = 'reset'
    WAITING_STEP = 'step'
    WAITING_VISUALS = "visuals"
    WAITING_SINGLE_VISUAL = "visual"
    WAITING_LED_OFF = "led_off"
    WAITING_LED_ON = "led_on"
    WAITING_MPP_SETUP = "motion_planner_policies_setup"
    WAITING_POLICY_RESET = "policy_reset_env"
    WAITING_POLICY_ACTION = "policy_action"
    WAITING_POLICY_DONE_SUBTASKS = "policy_done_subtasks"


class AsyncVectorEnv(VectorEnv):
    """Vectorized environment that runs multiple environments in parallel. It
    uses `multiprocessing` processes, and pipes for communication.

    Parameters
    ----------
    env_fns : iterable of callable
        Functions that create the environments.

    observation_space : `gym.spaces.Space` instance, optional
        Observation space of a single environment. If `None`, then the
        observation space of the first environment is taken.

    action_space : `gym.spaces.Space` instance, optional
        Action space of a single environment. If `None`, then the action space
        of the first environment is taken.

    shared_memory : bool (default: `True`)
        If `True`, then the observations from the worker processes are
        communicated back through shared variables. This can improve the
        efficiency if the observations are large (e.g. images).

    copy : bool (default: `True`)
        If `True`, then the `reset` and `step` methods return a copy of the
        observations.

    context : str, optional
        Context for multiprocessing. If `None`, then the default context is used.
        Only available in Python 3.
    """
    def __init__(self, env_fns, observation_space=None, action_space=None,
                 shared_memory=True, copy=True, context=None):
        try:
            ctx = mp.get_context(context)
        except AttributeError:
            logger.warn('Context switching for `multiprocessing` is not '
                'available in Python 2. Using the default context.')
            ctx = mp
        self.env_fns = env_fns
        self.shared_memory = shared_memory
        self.copy = copy

        if (observation_space is None) or (action_space is None):
            dummy_env = env_fns[0]()
            observation_space = observation_space or dummy_env.observation_space
            action_space = action_space or dummy_env.action_space
            dummy_env.close()
            del dummy_env
        super(AsyncVectorEnv, self).__init__(num_envs=len(env_fns),
            observation_space=observation_space, action_space=action_space)

        if self.shared_memory:
            _obs_buffer = create_shared_memory(self.single_observation_space,
                n=self.num_envs)
            self.observations = read_from_shared_memory(_obs_buffer,
                self.single_observation_space, n=self.num_envs)
        else:
            _obs_buffer = None
            self.observations = create_empty_array(
            	self.single_observation_space, n=self.num_envs, fn=np.zeros)

        self.parent_pipes, self.processes = [], []
        self.error_queue = ctx.Queue()
        target = _worker_shared_memory if self.shared_memory else _worker
        with clear_mpi_env_vars():
            for idx, env_fn in enumerate(self.env_fns):
                parent_pipe, child_pipe = ctx.Pipe()
                process = ctx.Process(target=target,
                    name='Worker<{0}>-{1}'.format(type(self).__name__, idx),
                    args=(idx, CloudpickleWrapper(env_fn), child_pipe,
                    parent_pipe, _obs_buffer, self.error_queue))

                self.parent_pipes.append(parent_pipe)
                self.processes.append(process)

                process.deamon = True
                process.start()
                child_pipe.close()

        self._state = AsyncState.DEFAULT
        self._check_observation_spaces()

    def seed(self, seeds=None):
        """
        Parameters
        ----------
        seeds : list of int, or int, optional
            Random seed for each individual environment. If `seeds` is a list of
            length `num_envs`, then the items of the list are chosen as random
            seeds. If `seeds` is an int, then each environment uses the random
            seed `seeds + n`, where `n` is the index of the environment (between
            `0` and `num_envs - 1`).
        """
        self._assert_is_running()
        if seeds is None:
            seeds = [None for _ in range(self.num_envs)]
        if isinstance(seeds, int):
            seeds = [seeds + i for i in range(self.num_envs)]
        assert len(seeds) == self.num_envs

        if self._state != AsyncState.DEFAULT:
            raise AlreadyPendingCallError('Calling `seed` while waiting '
                'for a pending call to `{0}` to complete.'.format(
                self._state.value), self._state.value)

        for pipe, seed in zip(self.parent_pipes, seeds):
            pipe.send(('seed', seed))
        for pipe in self.parent_pipes:
            pipe.recv()

    def reset_async(self):
        self._assert_is_running()
        if self._state != AsyncState.DEFAULT:
            raise AlreadyPendingCallError('Calling `reset_async` while waiting '
                'for a pending call to `{0}` to complete'.format(
                self._state.value), self._state.value)

        for pipe in self.parent_pipes:
            pipe.send(('reset', None))
        self._state = AsyncState.WAITING_RESET

    def reset_wait(self, timeout=None):
        """
        Parameters
        ----------
        timeout : int or float, optional
            Number of seconds before the call to `reset_wait` times out. If
            `None`, the call to `reset_wait` never times out.

        Returns
        -------
        observations : sample from `observation_space`
            A batch of observations from the vectorized environment.
        """
        self._assert_is_running()
        if self._state != AsyncState.WAITING_RESET:
            raise NoAsyncCallError('Calling `reset_wait` without any prior '
                'call to `reset_async`.', AsyncState.WAITING_RESET.value)

        if not self._poll(timeout):
            self._state = AsyncState.DEFAULT
            raise mp.TimeoutError('The call to `reset_wait` has timed out after '
                '{0} second{1}.'.format(timeout, 's' if timeout > 1 else ''))

        self._raise_if_errors()
        observations_list = [pipe.recv() for pipe in self.parent_pipes]
        self._state = AsyncState.DEFAULT

        if not self.shared_memory:
            concatenate(observations_list, self.observations,
                self.single_observation_space)

        return deepcopy(self.observations) if self.copy else self.observations

    def step_async(self, actions):
        """
        Parameters
        ----------
        actions : iterable of samples from `action_space`
            List of actions.
        """
        self._assert_is_running()
        if self._state != AsyncState.DEFAULT:
            raise AlreadyPendingCallError('Calling `step_async` while waiting '
                'for a pending call to `{0}` to complete.'.format(
                self._state.value), self._state.value)

        for pipe, action in zip(self.parent_pipes, actions):
            pipe.send(('step', action))
        self._state = AsyncState.WAITING_STEP

    def step_wait(self, timeout=None):
        """
        Parameters
        ----------
        timeout : int or float, optional
            Number of seconds before the call to `step_wait` times out. If
            `None`, the call to `step_wait` never times out.

        Returns
        -------
        observations : sample from `observation_space`
            A batch of observations from the vectorized environment.

        rewards : `np.ndarray` instance (dtype `np.float_`)
            A vector of rewards from the vectorized environment.

        dones : `np.ndarray` instance (dtype `np.bool_`)
            A vector whose entries indicate whether the episode has ended.

        infos : list of dict
            A list of auxiliary diagnostic informations.
        """
        self._assert_is_running()
        if self._state != AsyncState.WAITING_STEP:
            raise NoAsyncCallError('Calling `step_wait` without any prior call '
                'to `step_async`.', AsyncState.WAITING_STEP.value)

        if not self._poll(timeout):
            self._state = AsyncState.DEFAULT
            raise mp.TimeoutError('The call to `step_wait` has timed out after '
                '{0} second{1}.'.format(timeout, 's' if timeout > 1 else ''))

        self._raise_if_errors()
        results = [pipe.recv() for pipe in self.parent_pipes]
        self._state = AsyncState.DEFAULT
        observations_list, rewards, dones, infos = zip(*results)

        if not self.shared_memory:
            concatenate(observations_list, self.observations,
                self.single_observation_space)

        return (deepcopy(self.observations) if self.copy else self.observations,
                np.array(rewards), np.array(dones, dtype=np.bool_), infos)

    def close(self, timeout=None, terminate=False):
        """
        Parameters
        ----------
        timeout : int or float, optional
            Number of seconds before the call to `close` times out. If `None`,
            the call to `close` never times out. If the call to `close` times
            out, then all processes are terminated.

        terminate : bool (default: `False`)
            If `True`, then the `close` operation is forced and all processes
            are terminated.
        """
        if self.closed:
            return

        if self.viewer is not None:
            self.viewer.close()

        timeout = 0 if terminate else timeout
        try:
            if self._state != AsyncState.DEFAULT:
                logger.warn('Calling `close` while waiting for a pending '
                    'call to `{0}` to complete.'.format(self._state.value))
                function = getattr(self, '{0}_wait'.format(self._state.value))
                function(timeout)
        except mp.TimeoutError:
            terminate = True

        if terminate:
            for process in self.processes:
                if process.is_alive():
                    process.terminate()
        else:
            for pipe in self.parent_pipes:
                if not pipe.closed:
                    pipe.send(('close', None))
            for pipe in self.parent_pipes:
                if not pipe.closed:
                    pipe.recv()

        for pipe in self.parent_pipes:
            pipe.close()
        for process in self.processes:
            process.join()

        self.closed = True

    def _poll(self, timeout=None):
        self._assert_is_running()
        if timeout is not None:
            end_time = time.time() + timeout
        delta = None
        for pipe in self.parent_pipes:
            if timeout is not None:
                delta = max(end_time - time.time(), 0)
            if pipe.closed or (not pipe.poll(delta)):
                break
        else:
            return True
        return False

    def _check_observation_spaces(self):
        self._assert_is_running()
        for pipe in self.parent_pipes:
            pipe.send(('_check_observation_space', self.single_observation_space))
        if not all([pipe.recv() for pipe in self.parent_pipes]):
            raise RuntimeError('Some environments have an observation space '
                'different from `{0}`. In order to batch observations, the '
                'observation spaces from all environments must be '
                'equal.'.format(self.single_observation_space))

    def _assert_is_running(self):
        if self.closed:
            raise ClosedEnvironmentError('Trying to operate on `{0}`, after a '
                'call to `close()`.'.format(type(self).__name__))

    def _raise_if_errors(self):
        if not self.error_queue.empty():
            while not self.error_queue.empty():
                index, exctype, value = self.error_queue.get()
                logger.error('Received the following error from Worker-{0}: '
                    '{1}: {2}'.format(index, exctype.__name__, value))
                logger.error('Shutting down Worker-{0}.'.format(index))
                self.parent_pipes[index].close()
                self.parent_pipes[index] = None
            logger.error('Raising the last exception back to the main process.')
            raise exctype(value)

    def __del__(self):
        if hasattr(self, 'closed'):
            if not self.closed:
                self.close(terminate=True)

    # Robohive Multi Visuals but purely async
    def get_single_visuals(self, sub_env_idx, robot_idx=0):
        # TODO: add corresponding fn in robohive-multi base env, then debug all together.
        self._assert_is_running()
        pipe = self.parent_pipes[sub_env_idx]
        # Query visual obs for a single robot
        pipe.send(("get_single_visuals", robot_idx))
        return pipe.recv()


    # Robohive Multi Visuals (All in One)
    def get_visuals_async(self):
        self._assert_is_running()
        # TODO: wait call seems to cause some trouble, although it should not.
        # More investigation needed ? Or make it purely async ?
        # if self._state != AsyncState.DEFAULT:
        #     raise AlreadyPendingCallError('Calling `get_visuals_async` while waiting '
        #         'for a pending call to `{0}` to complete'.format(
        #         self._state.value), self._state.value)
        
        for pipe in self.parent_pipes:
            pipe.send(('visuals', None))
        self._state = AsyncState.WAITING_VISUALS

    def get_visuals_wait(self, timeout=None):
        self._assert_is_running()
        if self._state != AsyncState.WAITING_VISUALS:
            raise NoAsyncCallError('Calling `get_visuals_wait` without any prior '
                'call to `get_visuals_async`.', AsyncState.WAITING_VISUALS.value)

        if not self._poll(timeout):
            self._state = AsyncState.DEFAULT
            raise mp.TimeoutError('The call to `get_visuals_wait` has timed out after '
                '{0} second{1}.'.format(timeout, 's' if timeout > 1 else ''))

        self._raise_if_errors()
        # TODO: make it more flexible to support 4 envs * 4 robots for example
        visuals_dict = {
            f"rgb:franka{idx}_front_cam:256x256:2d": pipe.recv()["rgb:franka0_front_cam:256x256:2d"]
                for idx, pipe in enumerate(self.parent_pipes)
        }
        self._state = AsyncState.DEFAULT

        return visuals_dict

        # Naive method, for reference only
        # visual_list = [pipe.recv() for pipe in self.parent_pipes]
        # self._state = AsyncState.DEFAULT

        # # TODO: not sure if we get to use those ?
        # # if not self.shared_memory:
        # #     concatenate(observations_list, self.observations,
        # #         self.single_observation_space)

        # # return deepcopy(self.observations) if self.copy else self.observations
        # return visual_list

    def get_visuals(self):
        self.get_visuals_async()
        return self.get_visuals_wait()

    # Robohive Multi Robot Status LED
    ## LED OFF, purely async, no waiting
    def set_status_led_off(self, sub_env_idx, robot_idx=0):
        self._assert_is_running()
        self.parent_pipes[sub_env_idx].send(("led_off", robot_idx))

        return True

    ## LED ON, purely async, no waiting
    def set_status_led_on(self, sub_env_idx, robot_idx=0):
        self._assert_is_running()
        self.parent_pipes[sub_env_idx].send(("led_on", robot_idx))

        return True


    # Robohive Multi Setup MotionPlannerPolicies
    def setup_motion_planner_policies_async(self, horizon):
        self._assert_is_running()
        if self._state != AsyncState.DEFAULT:
            raise AlreadyPendingCallError('Calling `setup_motion_planner_policies_async` while waiting '
                'for a pending call to `{0}` to complete'.format(
                self._state.value), self._state.value)
        for pipe in self.parent_pipes:
            pipe.send(("setup_motion_planner_policies", horizon))
        self._state = AsyncState.WAITING_MPP_SETUP

    def setup_motion_planner_policies_wait(self, timeout=None):
        self._assert_is_running()
        if self._state != AsyncState.WAITING_MPP_SETUP:
            raise NoAsyncCallError('Calling `setup_motion_planner_policies_wait` without any prior '
                'call to `setup_motion_planner_policies_async`.', AsyncState.WAITING_MPP_SETUP.value)

        if not self._poll(timeout):
            self._state = AsyncState.DEFAULT
            raise mp.TimeoutError('The call to `setup_motion_planner_policies_wait` has timed out after '
                '{0} second{1}.'.format(timeout, 's' if timeout > 1 else ''))

        self._raise_if_errors()
        mpp_setup_results = [pipe.recv() for pipe in self.parent_pipes] # A list of policy, one for each robot in the sub env
        self._state = AsyncState.DEFAULT

        return mpp_setup_results

    def setup_motion_planner_policies(self, horizon):
        self.setup_motion_planner_policies_async(horizon)
        return self.setup_motion_planner_policies_wait()

    #
    def policy_reset_env_async(self):
        self._assert_is_running()
        if self._state != AsyncState.DEFAULT:
            raise AlreadyPendingCallError('Calling `policy_reset_env_async` while waiting '
                'for a pending call to `{0}` to complete'.format(
                self._state.value), self._state.value)
        for pipe in self.parent_pipes:
            pipe.send(("policy_reset_env", None))
        self._state = AsyncState.WAITING_POLICY_RESET

    def policy_reset_env_wait(self, timeout=None):
        self._assert_is_running()
        if self._state != AsyncState.WAITING_POLICY_RESET:
            raise NoAsyncCallError('Calling `policy_reset_env_wait` without any prior '
                'call to `policy_reset_env_async`.', AsyncState.WAITING_POLICY_RESET.value)

        if not self._poll(timeout):
            self._state = AsyncState.DEFAULT
            raise mp.TimeoutError('The call to `policy_reset_env_wait` has timed out after '
                '{0} second{1}.'.format(timeout, 's' if timeout > 1 else ''))

        self._raise_if_errors()
        policy_reset_results = [pipe.recv() for pipe in self.parent_pipes]
        self._state = AsyncState.DEFAULT

        return policy_reset_results

    def policy_reset_env(self):
        self.policy_reset_env_async()
        return self.policy_reset_env_wait()

    ##
    def policy_reset_env_single(self, sub_env_idx, robot_idx=0):
        self._assert_is_running()
        self.parent_pipes[sub_env_idx].send(("policy_reset_env_single", robot_idx))
    ##
    def policy_reset_done_subtasks(self, sub_env_idx, robot_idx=0):
        self._assert_is_running()
        self.parent_pipes[sub_env_idx].send(("policy_reset_done_subtasks", robot_idx))

    # TODO: purely async for each env ?
    def get_policy_action_async(self, obs, command, norm=True):
        self._assert_is_running()
        if self._state != AsyncState.DEFAULT:
            raise AlreadyPendingCallError('Calling `get_policy_action_async` while waiting '
                'for a pending call to `{0}` to complete'.format(
                self._state.value), self._state.value)
        for idx, pipe in enumerate(self.parent_pipes):
            # obs: should be of shape (n_sub_envs, n_robots_in_env) but
            # flattened for now, since not used for for motion planning anyway
            # command: List of len(n_robots)
            cmd_start_idx = idx * self.max_agents_per_env
            cmd_end_idx = cmd_start_idx + self.max_agents_per_env
            pipe.send(("get_policy_action", (obs, command[cmd_start_idx:cmd_end_idx], norm)))
        self._state = AsyncState.WAITING_POLICY_ACTION

    def get_policy_action_wait(self, timeout=None):
        self._assert_is_running()
        if self._state != AsyncState.WAITING_POLICY_ACTION:
            raise NoAsyncCallError('Calling `get_policy_action_wait` without any prior '
                'call to `get_policy_ation_async`.', AsyncState.WAITING_POLICY_ACTION.value)

        if not self._poll(timeout):
            self._state = AsyncState.DEFAULT
            raise mp.TimeoutError('The call to `get_policy_action_wait` has timed out after '
                '{0} second{1}.'.format(timeout, 's' if timeout > 1 else ''))

        self._raise_if_errors()
        action__subtask_dones = [pipe.recv() for pipe in self.parent_pipes]
        action, subtask_dones = [], []

        # Unpack
        for a_done_pair in action__subtask_dones:
            action.append(a_done_pair[0])
            subtask_dones.extend(a_done_pair[1])
        action = np.concatenate(action)
        self._state = AsyncState.DEFAULT

        return action, subtask_dones

    def get_policy_action(self, obs, command, norm=True):
        self.get_policy_action_async(obs, command, norm)
        return self.get_policy_action_wait()

    #
    def get_policy_done_subtasks_async(self):
        self._assert_is_running()
        if self._state != AsyncState.DEFAULT:
            raise AlreadyPendingCallError('Calling `get_policy_done_subtasks_async` while waiting '
                'for a pending call to `{0}` to complete'.format(
                self._state.value), self._state.value)
        for pipe in self.parent_pipes:
            pipe.send(("get_policy_done_subtasks", None))
        self._state = AsyncState.WAITING_POLICY_DONE_SUBTASKS

    def get_policy_done_subtasks_wait(self, timeout=None):
        self._assert_is_running()
        if self._state != AsyncState.WAITING_POLICY_DONE_SUBTASKS:
            raise NoAsyncCallError('Calling `get_policy_done_subtasks_wait` without any prior '
                'call to `get_policy_done_subtasks_async`.', AsyncState.WAITING_POLICY_DONE_SUBTASKS.value)

        if not self._poll(timeout):
            self._state = AsyncState.DEFAULT
            raise mp.TimeoutError('The call to `get_policy_done_subtasks_wait` has timed out after '
                '{0} second{1}.'.format(timeout, 's' if timeout > 1 else ''))

        self._raise_if_errors()
        policies_done_subtasks = [pipe.recv() for pipe in self.parent_pipes]
        self._state = AsyncState.DEFAULT

        # TODO: some re-shaping I guess
        return policies_done_subtasks

    def get_policy_done_subtasks(self):
        self.get_policy_done_subtasks_async()
        return self.get_policy_done_subtasks_wait()


# Overriding to add support for custom sub env function handling
def _worker(index, env_fn, pipe, parent_pipe, shared_memory, error_queue):
  assert shared_memory is None
  env = env_fn()
  parent_pipe.close()
  try:
    while True:
      command, data = pipe.recv()
      if command == 'reset':
        observation = env.reset()
        pipe.send(observation)
      elif command == 'step':
        observation, reward, done, info = env.step(data)
        if done:
            observation = env.reset()
        pipe.send((observation, reward, done, info))
      elif command == "visuals":
        pipe.send(env.get_visuals())
      elif command == "visual":
        # TODO: do we need a "visual_X" for each sub envs's robot ?
        raise NotImplementedError("Async query of sub envs visual not implemented yet !")
      elif command == "led_on":
        # data: idx_policy, i.e. the idx of the robot in the sub env
        pipe.send(env.status_led_on(data))
      elif command == "led_off":
        # data: idx_policy, i.e. the idx of the robot in the sub env
        pipe.send(env.status_led_off(data))
      elif command == "setup_motion_planner_policies":
        # data: horizon for motion planning
        pipe.send(env.setup_motion_planner_policies(data))
      elif command == "policy_reset_env":
        pipe.send(env.policy_reset_env())
      elif command == "policy_reset_env_single":
        # date: robot_idx in the env
        pipe.send(env.policy_reset_env_single(data))
      elif command == "get_policy_action":
        # data: (obs, command, norm)
        pipe.send(env.get_policy_action(*data))
      elif command == "get_policy_done_subtasks":
        pipe.send(env.get_policy_done_subtasks())
      elif command == 'seed':
        env.seed(data)
        pipe.send(None)
      elif command == 'close':
        pipe.send(None)
        break
      elif command == '_check_observation_space':
        pipe.send(data == env.observation_space)
      else:
        raise RuntimeError(f'Received unknown command `{command}`. Must '  # noqa: F524
                            'be one of {`reset`, `step`, `visuals`, `seed`, `close`, '
                            '`_check_observation_space`}.')
  except Exception:
    error_queue.put((index,) + sys.exc_info()[:2])
    pipe.send(None)
  finally:
    env.close()


def _worker_shared_memory(index, env_fn, pipe, parent_pipe, shared_memory, error_queue):
  assert shared_memory is not None
  env = env_fn()
  observation_space = env.observation_space
  parent_pipe.close()
  try:
    while True:
      command, data = pipe.recv()
      if command == 'reset':
        observation = env.reset()
        write_to_shared_memory(index, observation, shared_memory,
                                observation_space)
        pipe.send(None)
      elif command == 'step':
        observation, reward, done, info = env.step(data)
        if done:
            observation = env.reset()
        write_to_shared_memory(index, observation, shared_memory,
                                observation_space)
        pipe.send((None, reward, done, info))
      elif command == "visuals":
        pipe.send(env.get_visuals())
      elif command == "visual":
        # TODO: do we need a "visual_X" for each sub envs's robot ?
        raise NotImplementedError("Async query of sub envs visual not implemented yet !")
      elif command == "led_on":
        # data: idx_policy, i.e. the idx of the robot in the sub env
        pipe.send(env.status_led_on(data))
      elif command == "led_off":
        # data: idx_policy, i.e. the idx of the robot in the sub env
        pipe.send(env.status_led_off(data))
      elif command == "setup_motion_planner_policies":
        # data: horizon for motion planning
        pipe.send(env.setup_motion_planner_policies(data))
      elif command == "policy_reset_env":
        pipe.send(env.policy_reset_env())
      elif command == "policy_reset_env_single":
        # date: robot_idx in the env
        pipe.send(env.policy_reset_env_single(data))
      elif command == "get_policy_action":
        # data: (obs, command, norm)
        pipe.send(env.get_policy_action(*data))
      elif command == "get_policy_done_subtasks":
        pipe.send(env.get_policy_done_subtasks())
      elif command == 'seed':
        env.seed(data)
        pipe.send(None)
      elif command == 'close':
        pipe.send(None)
        break
      elif command == '_check_observation_space':
        pipe.send(data == observation_space)
      else:
        raise RuntimeError(f'Received unknown command `{command}`. Must '
                            'be one of {`reset`, `step`, `seed`, `close`, '
                            '`_check_observation_space`}.')
  except Exception:
    error_queue.put((index,) + sys.exc_info()[:2])
    pipe.send(None)
  finally:
    env.close()
