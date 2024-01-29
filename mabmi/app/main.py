from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from mabmi.app.app_state import AppState
from mabmi.routes import browser

app = FastAPI()
app.state = AppState()  # global state for the app
app.include_router(browser.router)
root = Path(__file__).parent.parent
app.mount("/static", StaticFiles(directory=root / "static"), name="static")
templates = Jinja2Templates(directory=root / "templates")


@app.get("/")
async def get(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "num_agents": app.state.num_agents})


# TODO: zeromq
# @app.websocket("/pupil")
# async def ws_pupil(websocket: WebSocket):
#     await websocket.accept()
#     ws_clients["pupil"] = websocket
#     print("/pupil: Client connected")
#     try:
#         while True:
#             data = await websocket.receive_json()
#             print(f"/pupil: received {data}")
#             # transfer the focus info to browser
#             await ws_clients["browser"].send_json(data)
#     except WebSocketDisconnect:
#         print("/pupil: Client disconnected")


# # TODO: zeromq
# @app.websocket("/webrtc-eeg")
# async def ws_eeg_webrtc(websocket: WebSocket):
#     await websocket.accept()
#     print("/webrtc-eeg: Client connected")
#     try:
#         # setup WebRTC connection
#         print("/webrtc-eeg: Setting up WebRTC connection...")
#         # receive offer
#         offer = json.loads(await websocket.receive_text())
#         # setup peer connection
#         pc = RTCPeerConnection()
#         await pc.setRemoteDescription(RTCSessionDescription(sdp=offer["sdp"], type="offer"))
#         # send answer
#         answer = await pc.createAnswer()
#         await pc.setLocalDescription(answer)
#         await websocket.send_text(
#             json.dumps(
#                 {
#                     "type": "answer",
#                     "sdp": pc.localDescription.sdp,
#                 }
#             )
#         )

#         # set the event handlers for data channel
#         @pc.on("datachannel")
#         def on_datachannel(channel):
#             data_channels["eeg"] = channel

#             @channel.on("message")
#             def on_message(message):
#                 assert isinstance(message, bytes)
#                 eeg_data = np.frombuffer(message, dtype=np.float32).reshape(n_chs, -1)
#                 print(f"/webrtc-eeg: received eeg {eeg_data.shape}")

#                 # TODO
#                 # decode to command
#                 command = np.random.randint(0, 4)
#                 # update command
#                 update_command({"type": "eeg", "command": command})  # TODO

#         peer_connections["eeg"] = pc

#     except WebSocketDisconnect:
#         print("/webrtc-eeg: Client disconnected")
#         pc = peer_connections.pop("eeg", None)
#         if pc is not None:
#             await pc.close()
#         data_channels.pop("eeg", None)


if __name__ == "__main__":
    import uvicorn

    # uvicorn.run("main:app", reload=True)
    uvicorn.run("main:app")
