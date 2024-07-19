import json
import time
from pathlib import Path

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
        self.history.append(data)

    def save_session(self, save_dir: Path): 
        """Saves the usernames and number of agents in session"""
        with jsonlines.open(save_dir / "history.jsonl", mode="w") as writer:
            writer.write_all(self.history)

        _data = self.userinfo.copy()

        usernames = list(set([x['username'] for x in self.history]))
        num_agents = len(set([x['agentId'] for x in self.history]))
        with jsonlines.open(save_dir / "info.json", mode="w") as writer:
            writer.write({"usernames": usernames, "numAgents": num_agents})

        return usernames
        
        

        
    def save_userinfo(self, user_log_dir, userid):
        """Save the user info and device selection to a json file."""

        _data = self.userinfo.copy()
        expid = user_log_dir.parts[-1]

        log_dir = user_log_dir.parents[1]
        exp_log_dir = log_dir / expid
    
        userinfo = _data[userid]['userinfo']
        deviceinfo = _data[userid]['deviceSelection']

        with open(user_log_dir / "info.json", "w") as f:
            json.dump(userinfo, f, indent=4)
        with open(user_log_dir / "deviceinfo.json", "w") as f:
            json.dump(deviceinfo, f, indent=4)

    
def compute_usermetrics(user_log_dir: Path, username, save=False): #change to directly take in history and info?
    """Computes metrics specific to user and saves the summary to a json file."""

    expid = user_log_dir.parts[-1]

    log_dir = user_log_dir.parents[1]
    exp_log_dir = log_dir / expid

    df_hist = pd.read_json(exp_log_dir / "history.jsonl", orient="records", lines=True)

    metrics = {}

    metrics[username] = {}

    metrics[username]["interactionTime"] = [v if v != "NaN" else None for v in df_hist[df_hist["username"]==username]["interactionTime"].fillna("NaN").to_list()]

    metrics[username]["commands"] = _compute_error_rate(
        df_hist[df_hist["username"]==username]["isNowAcceptable"].to_list(), df_hist[df_hist["username"]==username]["hasSubtaskNotDone"].to_list()
    )

    if save:
        #make directory if not exist
        user_log_dir.mkdir(parents=True, exist_ok=True)

        with open(user_log_dir / "metrics.json", "w") as f:
            json.dump(metrics[username], f, indent=4)

    return metrics

def compute_sessionmetrics(exp_log_dir: Path, info, save=False): #remove user metrics
    """
    Given the interaction history, compute metrics and save the summary to a json file 
    """
    df_hist = pd.read_json(exp_log_dir / "history.jsonl", orient="records", lines=True)

    metrics = {}

    metrics["total"] = {}

    metrics["total"]["taskCompletionTime"] = info
    metrics["total"]["interactionTime"] = [v if v != "NaN" else None for v in df_hist["interactionTime"].fillna("NaN").to_list()]
    metrics["total"]["commands"] = _compute_error_rate(
        df_hist["isNowAcceptable"].to_list(), df_hist["hasSubtaskNotDone"].to_list()
    )

    if save:
        with open(exp_log_dir / "metrics.json", "w") as f:
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
        "totalCount": total_cnt,
        "errorCount": err_cnt
    }
