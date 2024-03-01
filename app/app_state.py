from aiortc import RTCPeerConnection
from aiortc.contrib.media import MediaRelay


class AppState:
    def __init__(self) -> None:
        self.n_chs = 128
        self.num_agents = 4
        # self.num_agents = 1

        self.command: list[int] = [0] * self.num_agents
        self.focus: int | None = None  # updated only by websocket_endpoint_browser
        self.relay = MediaRelay()  # keep using the same instance for all connections
        self.pc: RTCPeerConnection | None = None

    def update_command(self, event, data):
        if self.focus is None:
            return

        if event == "eeg":
            # assume data is a command
            self.command[self.focus] = data
        elif event == "keydown":
            # assume data is a key
            if data == "0":
                self.command[self.focus] = 0
            elif data in ("1", "2", "3"):
                self.command[self.focus] = 1
