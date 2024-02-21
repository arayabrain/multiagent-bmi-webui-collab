from aiortc import VideoStreamTrack
from av import VideoFrame
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.app_state import AppState
from app.env import EnvRunner
from app.utils.webrtc import createPeerConnection, handle_answer, handle_candidate, handle_offer_request

router = APIRouter()


@router.websocket("/browser")
async def ws_browser(websocket: WebSocket):
    """Websocket endpoint for browser client

    Args:
        websocket (WebSocket): websocket connection from browser
    """
    await websocket.accept()
    print("/browser: Client connected")

    state: AppState = websocket.app.state
    state.ws_connections["browser"] = websocket

    # run environment
    env = EnvRunner(state)
    env.start()

    try:
        while True:
            data = await websocket.receive_json()

            if data["type"] in ("keyup", "keydown"):
                print(f"/browser: received {data}")
                state.update_command(data)
            elif data["type"] == "focus":
                print(f"/browser: received {data}")
                state.focus = data["focusId"]
            elif data["type"] == "eeg":
                print(f"/browser: received {data}")
                state.update_command(data)

            elif data["type"] == "webrtc-offer-request":
                pc = createPeerConnection(websocket)
                state.peer_connections["browser"] = pc

                # add stream tracks
                for i in range(state.num_agents):
                    track = state.relay.subscribe(ImageStreamTrack(env, i))
                    pc.addTransceiver(track, direction="sendonly")
                    print(f"Track {track.id} added to peer connection")

                await handle_offer_request(pc, websocket)
            elif data["type"] == "webrtc-answer":
                await handle_answer(pc, data)
            elif data["type"] == "webrtc-ice":
                await handle_candidate(pc, data)

    except WebSocketDisconnect:
        print("/browser: Client disconnected")
        state.ws_connections.pop("browser", None)
        await env.stop()
        pc = state.peer_connections.pop("browser", None)
        if pc:
            await pc.close()
            print("/browser: Peer connection closed")


class ImageStreamTrack(VideoStreamTrack):
    def __init__(self, env: EnvRunner, camera_idx: int):
        super().__init__()
        self.camera_idx = camera_idx

        # references to variables in EnvProcess
        self.cond = env.frame_update_cond
        self.frames = env.frames

    async def recv(self):
        global frames

        async with self.cond:
            await self.cond.wait()
            frame = self.frames[self.camera_idx]

        img = frame
        frame = VideoFrame.from_ndarray(img, format="rgb24")
        pts, time_base = await self.next_timestamp()
        frame.pts = pts
        frame.time_base = time_base

        return frame
