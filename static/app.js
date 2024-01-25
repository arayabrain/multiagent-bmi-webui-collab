let ws;
let retryCnt = 0;
const maxRetry = 3;

function connect() {
    ws = new WebSocket("ws://localhost:8000/browser");
    ws.onopen = function () {
        console.log("Websocket connected.");
        retryCnt = 0;  // reset retry counter on successful connection
    };
    ws.onmessage = function (event) {
        const data = JSON.parse(event.data);
        if (data.type == "image") {
            document.getElementById(data.id).src = "data:image/jpeg;base64," + data.data;
        }
        if (data.type == "gaze") {
            console.log("Websocket received: ", event.data);
            updateFocus(data.focusId);
        }
    };
    ws.onclose = function (e) {
        if (retryCnt < maxRetry) {
            console.log('Websocket disconnected. Reconnecting in 3 seconds...');
            setTimeout(function () {
                retryCnt++;
                connect();
            }, 3000); // try reconnecting in 3 second
        } else {
            console.error('Websocket disconnected. Maximum number of retries reached.');
        }
    };
    ws.onerror = function (e) {
        if (e.message != undefined) {
            console.error(`Websocket error:\n${e.message}`);
        }
        ws.close();
    };
}

let focusId = 0;
const updateFocus = (newId) => {
    if (newId == focusId) return;
    // remove border of the previous focused image
    if (focusId != null) {
        imgs[focusId].style.border = "2px solid transparent";
    }
    // update focusId
    focusId = newId;
    // set border to the new focused image
    if (focusId != null) {
        imgs[focusId].style.border = "2px solid red";
    }
    // notify focusId to the server
    if (ws.readyState == WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "focus", focusId: focusId }));
    }
}

connect();

// Focus the image when hovering the mouse cursor over it
let imgs;
document.addEventListener("DOMContentLoaded", function () {
    imgs = document.querySelectorAll('img.camera');
});
document.addEventListener('mousemove', function (event) {
    for (const [i, img] of imgs.entries()) {
        const rect = img.getBoundingClientRect();
        const isHover = rect.left <= event.pageX && event.pageX <= rect.right &&
            rect.top <= event.pageY && event.pageY <= rect.bottom;
        if (isHover) {
            updateFocus(i);
            break;
        }
    }
});

// Send pressed/released keys to the server
document.addEventListener('keydown', function (event) {
    if (ws.readyState != WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "keydown", key: event.key }));
});
document.addEventListener('keyup', function (event) {
    if (ws.readyState != WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "keyup", key: event.key }));
});