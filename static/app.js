let wsImage;
let wsInput;

function connect() {
    wsImage = new WebSocket("ws://localhost:8000/ws/image");
    wsImage.onopen = function () {
        console.log("/ws/image connected.");
    };
    wsImage.onmessage = function (event) {
        const data = JSON.parse(event.data);
        if (data.image_data && data.image_id) {
            document.getElementById(data.image_id).src = "data:image/jpeg;base64," + data.image_data;
        }
    };
    wsImage.onclose = function (e) {
        console.log('/ws/image disconnected. Reconnecting...');
        setTimeout(function () {
            connect();
        }, 1000); // try reconnecting in 1 second
    };
    wsImage.onerror = function (e) {
        console.error('/ws/image encountered error: ', e.message, 'Closing WebSocket');
        wsImage.close();
    };

    wsInput = new WebSocket("ws://localhost:8000/ws/input");
    wsInput.onopen = function () {
        console.log("/ws/input connected.");
    };
    wsInput.onmessage = function (event) {
        const data = JSON.parse(event.data);
        if (data.type == "gaze") {
            updateFocus(data.focus_id);
        }
    };
    wsInput.onclose = function (e) {
        console.log('/ws/input disconnected. Reconnecting...');
        setTimeout(function () {
            connect();
        }, 1000); // try reconnecting in 1 second
    };
    wsInput.onerror = function (e) {
        console.error('/ws/input encountered error: ', e.message, 'Closing WebSocket');
        wsInput.close();
    };
}

let focus_id = 0;
const updateFocus = (newId) => {
    imgs[focus_id].style.border = "2px solid transparent";
    focus_id = newId;
    imgs[focus_id].style.border = "2px solid red";
}

connect();

// Focus the image when hovering the mouse cursor over it
let imgs;
document.addEventListener("DOMContentLoaded", function () {
    imgs = document.querySelectorAll('img');
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
    if (wsInput.readyState != WebSocket.OPEN) return;
    wsInput.send(JSON.stringify({ type: "keydown", key: event.key, focus_id: focus_id }));
});
document.addEventListener('keyup', function (event) {
    if (wsInput.readyState != WebSocket.OPEN) return;
    wsInput.send(JSON.stringify({ type: "keyup", key: event.key, focus_id: focus_id }));
});