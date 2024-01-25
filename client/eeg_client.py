import asyncio
import json

import websockets
from aiortc import RTCPeerConnection, RTCSessionDescription
from mock_eeg import MockEEG

debug = False
if debug:
    import logging

    logging.basicConfig(level=logging.DEBUG)


is_running = True

mock = MockEEG(max_length=5000)
get_eeg = mock.pop


async def transfer_eeg():
    global is_running
    uri = "ws://localhost:8000/webrtc-eeg"
    max_retry = 3
    retry_cnt = 0
    buffer_full_thr = 1024 * 1024  # 1 MB

    while is_running and max_retry >= 0:
        try:
            async with websockets.connect(uri) as websocket:
                print("Websocket Connected.")
                retry_cnt = 0  # reset retry counter on successful connection

                _, dc = await setup_webrtc(websocket)

                # send eeg data
                while dc.readyState == "open":
                    eeg_data = get_eeg()
                    if eeg_data is not None:
                        eeg_bytes = eeg_data.tobytes()
                        if dc.bufferedAmount < buffer_full_thr:
                            dc.send(eeg_bytes)
                        else:
                            print("Buffer is full, skipping")
                    await asyncio.sleep(0.1)  # TODO

                # TODO: cannot detect connection closed

        except websockets.exceptions.ConnectionClosedError:
            if retry_cnt < max_retry:
                print("Connection closed. Reconnecting in 3 seconds...")
                await asyncio.sleep(3)
                retry_cnt += 1
            else:
                print("Maximum number of retries reached. Exiting...")
                is_running = False
        except ConnectionRefusedError:
            print("Connection refused. Exiting...")
            is_running = False


async def setup_webrtc(websocket: websockets.WebSocketClientProtocol):
    pc = RTCPeerConnection()
    dc = pc.createDataChannel("eeg")

    # setup WebRTC connection
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    await websocket.send(
        json.dumps(
            {
                "type": "offer",
                "sdp": pc.localDescription.sdp,
            }
        )
    )
    answer = json.loads(await websocket.recv())
    await pc.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type="answer"))
    print("WebRTC Connected.")

    # wait for data channel to open
    while dc.readyState != "open":
        await asyncio.sleep(0.1)
    print("DataChannel Opened.")

    return pc, dc


async def main():
    mock.start()
    await transfer_eeg()
    mock.stop()


if __name__ == "__main__":
    asyncio.run(main(), debug=debug)
