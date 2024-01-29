let ws;
let pc;
let retryCnt = 0;
let onTrackCnt = 0;
const maxRetry = 3;
let focusId = 0;
let videos;

document.addEventListener("DOMContentLoaded", () => {
    videos = document.querySelectorAll('video');

    connect();

    // Focus the image when hovering the mouse cursor over it
    document.addEventListener('mousemove', (event) => {
        for (const [i, video] of videos.entries()) {
            const rect = video.getBoundingClientRect();
            const isHover = rect.left <= event.pageX && event.pageX <= rect.right &&
                rect.top <= event.pageY && event.pageY <= rect.bottom;
            if (isHover) {
                updateFocus(i);
                break;
            }
        }
    });
    // Send pressed/released keys to the server
    document.addEventListener('keydown', (event) => {
        if (ws.readyState != WebSocket.OPEN) return;
        ws.send(JSON.stringify({ type: "keydown", key: event.key }));
    });
    document.addEventListener('keyup', (event) => {
        if (ws.readyState != WebSocket.OPEN) return;
        ws.send(JSON.stringify({ type: "keyup", key: event.key }));
    });
});

const connect = () => {
    ws = new WebSocket("ws://localhost:8000/browser");

    ws.onopen = async () => {
        console.log("Websocket connected.");
        retryCnt = 0;  // reset retry counter on successful connection

        // request WebRTC offer to the server
        ws.send(JSON.stringify({ type: "webrtc-offer-request" }));
    };
    ws.onmessage = async (event) => {
        const data = JSON.parse(event.data);
        if (data.type == "gaze") {
            console.log("Websocket received: ", event.data);
            updateFocus(data.focusId);
        } else if (data.type == "webrtc-offer") {
            console.log("WebRTC offer received");
            pc = setupPeerConnection();
            await handleOffer(data);
        } else if (data.type == "webrtc-ice") {
            await handleRemoteIce(data);
        }
    };
    ws.onclose = (e) => {
        if (retryCnt < maxRetry) {
            console.log('Websocket disconnected. Reconnecting in 3 seconds...');
            setTimeout(() => {
                retryCnt++;
                connect();
            }, 3000); // try reconnecting in 3 second
        } else {
            console.error('Websocket disconnected. Maximum number of retries reached.');
        }
    };
    ws.onerror = (e) => {
        if (e.message != undefined) {
            console.error(`Websocket error:\n${e.message}`);
        }
        ws.close();
    };
}

const setupPeerConnection = () => {
    pc = new RTCPeerConnection();
    onTrackCnt = 0;

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
    pc.connectionstatechange = (event) => {
        console.log(`Connection state: ${pc.connectionState}`);
    }
    pc.iceconnectionstatechange = (event) => {
        console.log(`ICE connection state: ${pc.iceConnectionState}`);
    }

    return pc;
}

const handleOffer = async (data) => {
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

const handleRemoteIce = async (data) => {
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

const updateFocus = (newId) => {
    if (newId == focusId) return;
    // remove border of the previous focused image
    if (focusId != null) {
        videos[focusId].style.border = "2px solid transparent";
    }
    // update focusId
    focusId = newId;
    // set border to the new focused image
    if (focusId != null) {
        videos[focusId].style.border = "2px solid red";
    }
    // notify focusId to the server
    if (ws.readyState == WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "focus", focusId: focusId }));
    }
}

