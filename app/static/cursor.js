
let sockEnv;
let cursor, videos;
let focusId = null;
const interactionTimer = new easytimer.Timer();
const interactionTimeHistory = [];

// initialize the timer config
interactionTimer.start({ precision: 'secondTenths' });
interactionTimer.stop();

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
    x = Math.max(hw, Math.min(x, window.innerWidth - hw - 1));  // -hw-1 so that scroll bars do not appear
    y = Math.max(hh, Math.min(y, window.innerHeight - hh - 1));

    cursor.style.left = `${x}px`;
    cursor.style.top = `${y}px`;

    // Focus the camera when the cursor is over it
    // TODO: optimize this process
    let newId = null;
    for (const [i, video] of videos.entries()) {
        const rect = video.getBoundingClientRect();
        if (x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom) {
            newId = i;
            break;
        }
    }
    if (newId != focusId) _updateAndNotifyFocus(newId);
}

const _updateAndNotifyFocus = (newId) => {
    // remove border of the previous focused image
    if (focusId != null) {
        videos[focusId].style.border = "2px solid transparent";
    }
    // set border to the new focused image
    if (newId != null) {
        videos[newId].style.border = "2px solid red";
    }
    // update focusId
    focusId = newId;

    // notify focusId to the server
    if (sockEnv === undefined) {
        console.error("sockEnv is not set. Call setSockEnv first.")
        return;
    }
    if (sockEnv.connected) sockEnv.emit('focus', focusId);

    // start the timer
    resetInteractionTimer();
}

export const recordInteractionTime = () => {
    interactionTimer.pause();
    const sec = interactionTimer.getTotalTimeValues().secondTenths / 10;
    interactionTimeHistory.push(sec);
    return sec;
}

export const resetInteractionTimer = () => interactionTimer.reset();

export const getInteractionTimeStats = () => {
    let mean = null, std = null;
    const len = interactionTimeHistory.length;
    if (len !== 0) {
        mean = math.mean(interactionTimeHistory);
        std = math.std(interactionTimeHistory);
    }
    return { len, mean, std };
}

export const resetInteractionTimeHistory = () => {
    interactionTimeHistory.length = 0;
}
