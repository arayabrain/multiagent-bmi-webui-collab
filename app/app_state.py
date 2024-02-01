from typing import Dict, List

from aiortc import RTCPeerConnection
from aiortc.contrib.media import MediaRelay
from fastapi import WebSocket


class AppState:
    def __init__(self) -> None:
        self.n_chs = 128
        self.num_agents = 4

        self.command: List[int] = [0] * self.num_agents
        self.focus: int | None = None  # updated only by websocket_endpoint_browser
        self.relay = MediaRelay()  # keep using the same instance for all connections

        self.ws_connections: Dict[str, WebSocket] = {}
        self.peer_connections: Dict[str, RTCPeerConnection] = {}
        self.data_channels: Dict[str, RTCPeerConnection] = {}

    def update_command(self, data):
        if self.focus is None:
            return

        if data["type"] == "eeg":
            self.command[self.focus] = data["command"]
        elif data["type"] == "keydown":
            if data["key"] == "0":
                self.command[self.focus] = 0
            elif data["key"] in ("1", "2", "3"):
                self.command[self.focus] = 1
