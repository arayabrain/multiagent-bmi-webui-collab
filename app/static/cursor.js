let sockEnv;
let cursor, videos;
let focusId = null;

document.addEventListener("DOMContentLoaded", () => {
    cursor = document.getElementById('cursor');
    videos = document.querySelectorAll('video');
});

export const setSockEnv = (sock) => sockEnv = sock;

export const getFocusId = () => focusId;

export const updateCursorAndFocus = (x, y, isDelta = false) => {
    if (cursor.style.display != 'block')
        cursor.style.display = 'block';

    if (isDelta) {
        // x and y are diff values from the previous position
        x += cursor.offsetLeft;
        y += cursor.offsetTop;
    }

    // Limit the cursor position within the window
    const hw = cursor.offsetWidth / 2;
    const hh = cursor.offsetHeight / 2;
    x = Math.max(hw, Math.min(x, window.innerWidth - hw));
    y = Math.max(hh, Math.min(y, window.innerHeight - hh));

    cursor.style.left = `${x}px`;
    cursor.style.top = `${y}px`;

    // Focus the camera when the cursor is over it
    // TODO: optimize this process
    for (const [i, video] of videos.entries()) {
        const rect = video.getBoundingClientRect();
        if (x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom) {
            updateAndNotifyFocus(i);
            break;
        }
    }
}

const updateAndNotifyFocus = (newId) => {
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
    if (sockEnv === undefined) {
        console.error("sockEnv is not set. Call setSockEnv first.")
        return;
    }
    if (sockEnv.connected) sockEnv.emit('focus', focusId);
}