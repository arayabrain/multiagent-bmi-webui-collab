import { handleOffer, handleRemoteIce, setupPeerConnection } from './webrtc.js';

let wsEnv, wsGaze;
const maxRetry = 3;
const reconnectInterval = 3000;
let focusId = 0;
let videos;
let toggleGaze;
let aprilTags;

document.addEventListener("DOMContentLoaded", () => {
    videos = document.querySelectorAll('video');
    toggleGaze = document.getElementById('toggle-eyetracker');
    aprilTags = document.getElementsByClassName("apriltag");

    connectEnv();

    toggleGaze.addEventListener('change', () => {
        if (toggleGaze.checked) {
            connectGaze();
            showAprilTags();
        } else {
            if (wsGaze.readyState == WebSocket.OPEN) wsGaze.close();
            hideAprilTags();
        }
    });

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
        if (wsEnv.readyState != WebSocket.OPEN) return;
        wsEnv.send(JSON.stringify({ type: "keydown", key: event.key }));
    });
    document.addEventListener('keyup', (event) => {
        if (wsEnv.readyState != WebSocket.OPEN) return;
        wsEnv.send(JSON.stringify({ type: "keyup", key: event.key }));
    });
});

const connectEnv = (retryCnt = 0) => {
    // wsEnv: websocket for communication with the environment server
    // - WebRTC signaling
    // - focus update notification
    wsEnv = new WebSocket(getWsUrl(8000) + "/browser");
    let pc;

    wsEnv.onopen = async () => {
        console.log("wsEnv: Connected");
        retryCnt = 0;  // reset retry counter on successful connection

        // request WebRTC offer to the server
        wsEnv.send(JSON.stringify({ type: "webrtc-offer-request" }));
    };
    wsEnv.onmessage = async (event) => {
        const data = JSON.parse(event.data);
        if (data.type == "webrtc-offer") {
            console.log("wsEnv: WebRTC offer received");
            pc = setupPeerConnection(wsEnv, videos);
            await handleOffer(wsEnv, pc, data);
        } else if (data.type == "webrtc-ice") {
            await handleRemoteIce(pc, data);
        }
    };
    wsEnv.onclose = async (e) => {
        if (retryCnt < maxRetry) {
            console.log('wsEnv: Disconnected. Reconnecting in 3 seconds...');
            await sleep(reconnectInterval);
            connectEnv(retryCnt + 1);
        } else {
            console.error('wsEnv: Disconnected. Maximum number of retries reached.');
        }
    };
    wsEnv.onerror = (e) => {
        if (e.message != undefined) {
            console.error(`wsEnv: Error\n${e.message}`);
        }
        wsEnv.close();
    };
}

const connectGaze = (retryCnt = 0) => {
    // wsGaze: websocket for communication with the gaze server
    wsGaze = new WebSocket(getWsUrl(8001));

    wsGaze.onopen = () => {
        console.log("wsGaze: connected");
        retryCnt = 0;  // reset retry counter on successful connection
    };
    wsGaze.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === "gaze") {
            console.log("Gaze data received: ", data);
            updateFocus(data.focusId);
        }
    };
    wsGaze.onclose = async (e) => {
        if (!toggleGaze.checked) {
            console.log('wsGaze: Disconnected by user');
            return;
        }

        if (retryCnt < maxRetry) {
            console.log('wsGaze: Disconnected. Reconnecting in 3 seconds...');
            await sleep(reconnectInterval);
            connectGaze(retryCnt + 1);
        } else {
            console.error('wsGaze: Disconnected. Maximum number of retries reached.');
        }
    };
    wsGaze.onerror = (e) => {
        if (e.message != undefined) {
            console.error(`wsGaze: Error\n${e.message}`);
        }
        wsGaze.close();
    };
};

const showAprilTags = () => {
    Array.from(aprilTags).forEach((tag) => {
        tag.style.display = 'block';
    });
}

const hideAprilTags = () => {
    Array.from(aprilTags).forEach((tag) => {
        tag.style.display = 'none';
    });
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
    if (wsEnv.readyState == WebSocket.OPEN) {
        wsEnv.send(JSON.stringify({ type: "focus", focusId: focusId }));
    }
}

const getWsUrl = (port) => {
    const loc = window.location;
    const wsProtocol = loc.protocol === "https:" ? "wss" : "ws";
    return `${wsProtocol}://${loc.hostname}:${port}`;
}

const sleep = (msec) => new Promise(resolve => setTimeout(resolve, msec));
