from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.sdp import candidate_from_sdp
from fastapi import WebSocket


def createPeerConnection(websocket: WebSocket):
    pc = RTCPeerConnection()

    @pc.on("icecandidate")
    async def on_icecandidate(candidate):
        data = {
            "type": "webrtc-ice",
            "candidate": None,
        }
        if candidate:
            data["candidate"] = {
                "candidate": candidate.to_sdp(),
                "sdpMid": candidate.sdpMid,
                "sdpMLineIndex": candidate.sdpMLineIndex,
            }
        await websocket.send_json(data)
        print("/browser: Sent ICE candidate info")

    @pc.on("connectionstatechange")
    def on_connectionstatechange():
        print(f"/browser: Connection state: {pc.connectionState}")

    @pc.on("iceconnectionstatechange")
    def on_iceconnectionstatechange():
        print(f"/browser: ICE connection state: {pc.iceConnectionState}")

    return pc


async def handle_offer_request(pc: RTCPeerConnection, websocket: WebSocket):
    print("/browser: Received offer request")
    offer = await pc.createOffer()
    await websocket.send_json(
        {
            "type": "webrtc-offer",
            "sdp": offer.sdp,
        }
    )
    print("/browser: Sent WebRTC offer. Setting local description...")
    await pc.setLocalDescription(offer)  # slow; takes 5s
    print("Local description set.")


async def handle_answer(pc: RTCPeerConnection, data):
    print("/browser: Received WebRTC answer")
    await pc.setRemoteDescription(RTCSessionDescription(type="answer", sdp=data["sdp"]))


async def handle_candidate(pc, data):
    print("/browser: Received ICE candidate info")
    if data["candidate"] is None:
        # candidate is None when all candidates have been received
        print("/browser: All candidates received")
        # await pc.addIceCandidate(None)  # error
    else:
        candidate = candidate_from_sdp(data["candidate"])
        candidate.sdpMid = data["sdpMid"]
        candidate.sdpMLineIndex = data["sdpMLineIndex"]
        await pc.addIceCandidate(candidate)
