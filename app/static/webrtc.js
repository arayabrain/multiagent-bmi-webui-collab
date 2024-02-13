export const setupPeerConnection = (ws, videos) => {
    const pc = new RTCPeerConnection();
    let onTrackCnt = 0;

    pc.onicecandidate = ({ candidate }) => {
        const data = {
            type: 'webrtc-ice',
            candidate: null,
        }
        if (candidate) {
            data.candidate = candidate.candidate;
            data.sdpMid = candidate.sdpMid;
            data.sdpMLineIndex = candidate.sdpMLineIndex;
        }
        ws.send(JSON.stringify(data));
    }
    pc.ontrack = (event) => {
        // called when remote stream added to peer connection
        // set source of corresponding video element
        const track = event.track;
        console.log(`Track ${onTrackCnt} - readyState: ${track.readyState}, muted: ${track.muted}, id: ${track.id}`);
        videos[onTrackCnt].srcObject = new MediaStream([track]);
        onTrackCnt++;
    }
    pc.onsignalingstatechange = (event) => {
        console.log(`Signaling state: ${pc.signalingState}`);
    }
    pc.onconnectionstatechange = (event) => {
        console.log(`Connection state: ${pc.connectionState}`);
    }
    pc.onicegatheringstatechange = (event) => {
        console.log(`ICE gathering state: ${pc.iceGatheringState}`);
    }
    pc.oniceconnectionstatechange = (event) => {
        console.log(`ICE connection state: ${pc.iceConnectionState}`);
    }

    return pc;
}

export const handleOffer = async (ws, pc, data) => {
    if (!pc) {
        console.error('no peerconnection');
        return;
    }
    await pc.setRemoteDescription({ type: "offer", sdp: data.sdp });
    const answer = await pc.createAnswer();
    ws.send(JSON.stringify({ type: "webrtc-answer", sdp: answer.sdp }));
    console.log("WebRTC answer sent.");
    await pc.setLocalDescription(answer);
}

export const handleRemoteIce = async (pc, data) => {
    if (!pc) {
        console.error('no peerconnection');
        return;
    }
    if (!data.candidate) {
        // ice gathering completed
        await pc.addIceCandidate(null);
        console.log("All ICE candidate received");
    } else {
        await pc.addIceCandidate({ type: 'candidate', candidate: data.candidate });
        console.log("ICE candidate received");
    }
}
