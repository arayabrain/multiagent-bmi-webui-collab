import { handleOffer, handleRemoteIce, setupPeerConnection } from './webrtc.js';

let wsEnv, sockGaze, sockEEG;
// sockGaze: socket for communication with the gaze server
const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
const maxRetry = 3;
const reconnectInterval = 3000;
let focusId = 0;
let videos;
let toggleGaze, toggleEEG;
let aprilTags;

document.addEventListener("DOMContentLoaded", () => {
    videos = document.querySelectorAll('video');
    toggleGaze = document.getElementById('toggle-eyetracker');
    toggleEEG = document.getElementById('toggle-eeg');
    aprilTags = document.getElementsByClassName("apriltag");

    connectEnv();

    toggleGaze.addEventListener('change', () => {
        if (toggleGaze.checked) {
            sockGaze = io.connect('http://localhost:8001', { transports: ['websocket'] });
            sockGaze.on('connect', () => {
                console.log("Gaze server connected");
            });
            sockGaze.on('disconnect', () => {
                console.log("Gaze server disconnected");
            });
            sockGaze.on('reconnect_attempt', () => {  // TODO: not working
                console.log("Gaze server reconnecting...");
            });
            sockGaze.on('gaze', (data) => {
                console.log("Gaze data received: ", data);
                updateFocus(data.focusId);
            });
            showAprilTags();
        } else {
            if (sockGaze.connected) sockGaze.disconnect();
            hideAprilTags();
        }
    });

    toggleEEG.addEventListener('change', () => {
        if (toggleEEG.checked) {
            sockEEG = io.connect('http://localhost:8002', { transports: ['websocket'] });
            sockEEG.on('connect', () => {
                console.log("EEG server connected");
            });
            sockEEG.on('disconnect', () => {
                console.log("EEG server disconnected");
            });
            sockEEG.on('reconnect_attempt', () => {  // TODO: not working
                console.log("EEG server reconnecting...");
            });
            sockEEG.on('eeg', (data) => {
                console.log("EEG data received: ", data);
                wsEnv.send(JSON.stringify({ type: "eeg", command: data.command }));  // TODO
            });
        } else {
            if (sockEEG.connected) sockEEG.disconnect();
        }
    });

    // Focus the image when hovering the mouse cursor over it
    document.addEventListener('mousemove', (event) => {
        // TODO: optimize this
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
    wsEnv = new WebSocket(`${wsProtocol}://${window.location.hostname}:${8000}/browser`);
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

const sleep = (msec) => new Promise(resolve => setTimeout(resolve, msec));
