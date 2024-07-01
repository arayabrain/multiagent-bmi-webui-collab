import json
import time
from pathlib import Path
from typing import Dict, Optional

import jsonlines
import numpy as np
import pandas as pd


class taskCompletionTimer:
    def __init__(self):
        self.start_time = None
        self.elapsed = None

    def start(self):
        self.start_time = time.time()
        self.elapsed = None

    def stop(self):
        if self.start_time is None:
            raise ValueError("Timer is not started")
        self.elapsed = time.time() - self.start_time


class InteractionRecorder:
    def __init__(self):
        self.history = []
        self.userinfo = {}

    def reset(self):
        self.history = []
        self.userinfo = {}

    def add_user(self, user_id: str, userinfo: dict):
        self.userinfo[user_id] = userinfo

    def record(self, user_id: str, data: dict):
        assert user_id in self.userinfo, "User not added"
        self.history.append({"userId": user_id, **data})

    def save_session(self, save_dir: Path): 
        """Saves the usernames and number of agents in session"""
        with jsonlines.open(save_dir / "history.jsonl", mode="w") as writer:
            writer.write_all(self.history)

        _data = self.userinfo.copy()
        #get list of usernames and number of agents from history.jsonl
        usernames = list(set([x['username'] for x in self.history]))
        num_agents = len(set([x['agentId'] for x in self.history]))
        with jsonlines.open(save_dir / "info.json", mode="w") as writer:
            writer.write({"usernames": usernames, "num_agents": num_agents})
        print("Session saved")
        
        

        
    def save_userinfo(self, user_log_dir, userid):
        """Save the user info and device selection to a json file."""

        _data = self.userinfo.copy()

        username = user_log_dir.parts[-2]
        expid = user_log_dir.parts[-1]

        log_dir = user_log_dir.parents[1]
        exp_log_dir = log_dir / expid
    
        userinfo = _data[userid]['userinfo']
        deviceinfo = _data[userid]['deviceSelection']

        with open(user_log_dir / "userinfo.json", "w") as f:
            json.dump(userinfo, f, indent=4)
        with open(user_log_dir / "deviceinfo.json", "w") as f:
            json.dump(deviceinfo, f, indent=4)

    
def compute_usermetrics(user_log_dir: Path, userid, save=False): #change to directly take in history and info?
    """Computes metrics specific to user and saves the summary to a json file."""

    username = user_log_dir.parts[-2]
    expid = user_log_dir.parts[-1]

    log_dir = user_log_dir.parents[1]
    exp_log_dir = log_dir / expid

    df_hist = pd.read_json(exp_log_dir / "history.jsonl", orient="records", lines=True)

    metrics = {}

    metrics[userid] = {}

    grouped = df_hist.groupby("userId")

    metrics[userid]["interactionTime"] = df_hist[df_hist["userId"]==userid]["interactionTime"].to_list()

    metrics[userid]["commands"] = _compute_error_rate(
        df_hist[df_hist["userId"]==userid]["isNowAcceptable"].to_list(), df_hist[df_hist["userId"]==userid]["hasSubtaskNotDone"].to_list()
    )

    if save:
        #make directory if not exist
        user_log_dir.mkdir(parents=True, exist_ok=True)

        with open(user_log_dir / "usermetrics.json", "w") as f:
            json.dump(metrics[userid], f, indent=4)

    return metrics

def compute_sessionmetrics(exp_log_dir: Path, info, save=False): #remove user metrics
    """
    Given the interaction history, compute metrics and save the summary to a json file 
    """
    expid = exp_log_dir.parts[-1]
    df_hist = pd.read_json(exp_log_dir / "history.jsonl", orient="records", lines=True)
    #df_info = pd.read_json(exp_log_dir / "info.json")

    # user_ids = df_info.columns.to_list() # user ids 
    # if "total" not in user_ids:
    #     user_ids.append("total")

    metrics = {}

    # metrics = {}
    # for user_id in user_ids:
    #     metrics[user_id] = {}

    metrics["total"] = {}

    grouped = df_hist.groupby("userId")

    # task completion time
    metrics["total"]["taskCompletionTime"] = info

    # interaction time stats
    # for user_id, times in grouped["interactionTime"]:
    #     metrics[user_id]["interactionTime"] = times.to_list()
    metrics["total"]["interactionTime"] = df_hist["interactionTime"].to_list()

    # error rates
    # for (user_id, accs), (_, nds) in zip(grouped["isNowAcceptable"], grouped["hasSubtaskNotDone"]):
    #     metrics[user_id]["commands"] = _compute_error_rate(accs.to_list(), nds.to_list())
    metrics["total"]["commands"] = _compute_error_rate(
        df_hist["isNowAcceptable"].to_list(), df_hist["hasSubtaskNotDone"].to_list()
    )

    if save:
        with open(exp_log_dir / "sessionmetrics.json", "w") as f:
            json.dump(metrics['total'], f, indent=4)

    return metrics


def _compute_interaction_time_stats(interaction_time_ls: list):
    return {
        "mean": np.mean(interaction_time_ls),
        "std": np.std(interaction_time_ls),
    }


def _compute_error_rate(is_now_acceptable_ls: list, has_subtask_not_done_ls: list):
    total_cnt = 0
    err_cnt = 0
    for acc, not_done in zip(is_now_acceptable_ls, has_subtask_not_done_ls):
        if not acc:
            continue  # not count as interaction
        total_cnt += 1
        if not not_done:
            err_cnt += 1
    return {
        "total_count": total_cnt,
        "error_count": err_cnt
    }
