import socketio
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription  # , RTCIceServer
from aiortc.sdp import candidate_from_sdp


def createPeerConnection(sio: socketio.AsyncServer, sid: str):
    config = RTCConfiguration()
    # config.iceServers = [RTCIceServer(urls="stun:stun.l.google.com:19302")]
    pc = RTCPeerConnection(config)

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
        await sio.emit("webrtc-ice", data, to=sid)

    @pc.on("signalingstatechange")
    def on_signalingstatechange():
        print(f"/browser: Signaling state: {pc.signalingState}")

    @pc.on("connectionstatechange")
    def on_connectionstatechange():
        print(f"/browser: Connection state: {pc.connectionState}")

    @pc.on("icegatheringstatechange")
    def on_icegatheringstatechange():
        print(f"/browser: ICE gathering state: {pc.iceGatheringState}")

    @pc.on("iceconnectionstatechange")
    def on_iceconnectionstatechange():
        print(f"/browser: ICE connection state: {pc.iceConnectionState}")

    return pc


async def handle_offer_request(pc: RTCPeerConnection, sio: socketio.AsyncServer, sid: str):
    print("/browser: Received offer request")
    offer = await pc.createOffer()
    print("Setting local description...")
    await pc.setLocalDescription(offer)  # slow; takes 5s
    print("Local description set.")
    await sio.emit("webrtc-offer", {"sdp": offer.sdp}, to=sid)
    print("/browser: Sent WebRTC offer.")


async def handle_answer(pc: RTCPeerConnection, data):
    print("/browser: Received WebRTC answer")
    if pc.signalingState == "stable":
        # TODO
        return
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
