import { updateCursorAndFocus } from './cursor.js';
import { updateConnectionStatusElement } from './utils.js';
let sockGaze;
let surfaceOrigin, surfaceSize;

export const onToggleGaze = (checked) => {
    if (checked) {
        updateConnectionStatusElement('connecting', 'toggle-gaze');
        sockGaze = io.connect(`http://localhost:8001`, { transports: ['websocket'] });  // TODO: https?
        sockGaze.on('connect', () => {
            updateConnectionStatusElement('connected', 'toggle-gaze');
            console.log("Gaze server connected");
        });
        sockGaze.on('disconnect', () => {
            updateConnectionStatusElement('disconnected', 'toggle-gaze');
            console.log("Gaze server disconnected");
        });
        sockGaze.on('reconnect_attempt', () => {  // TODO: not working
            console.log("Gaze server reconnecting...");
        });
        sockGaze.on('gaze', (gaze) => {
            const mappedGaze = mapGazeToSurface(gaze.x, gaze.y);
            updateCursorAndFocus(...mappedGaze);
        });
        showAprilTags();
    } else {
        if (sockGaze.connected) sockGaze.disconnect();
        hideAprilTags();
    }
}

const showAprilTags = () => {
    [...document.getElementsByClassName('apriltag')].forEach((tag) => {
        tag.style.display = 'block';
    });

    // get surface coordinates
    const topLeftTag = document.querySelector('.apriltag.top-left');
    const bottomRightTag = document.querySelector('.apriltag.bottom-right');
    const { top, left } = topLeftTag.getBoundingClientRect();
    const { bottom, right } = bottomRightTag.getBoundingClientRect();
    const margin = topLeftTag.width * 0.2;  // width of white margin + black border of apriltag
    const [left_, top_] = [left + margin, top + margin];
    const [right_, bottom_] = [right - margin, bottom - margin];
    surfaceOrigin = [left_, top_];
    surfaceSize = [right_ - left_, bottom_ - top_];
}

const hideAprilTags = () => {
    [...document.getElementsByClassName('apriltag')].forEach((tag) => {
        tag.style.display = 'none';
    });
}

const mapGazeToSurface = (x, y) => {
    // [x, y] in the range of [0, 1]^2
    const gaze = [
        surfaceOrigin[0] + surfaceSize[0] * x,
        surfaceOrigin[1] + surfaceSize[1] * y,
    ];
    return gaze;
}
