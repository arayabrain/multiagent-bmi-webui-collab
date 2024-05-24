import { updateCursorAndFocus } from './cursor.js';
import { updateDeviceStatus } from './utils.js';

const deviceName = 'Gaze';
const eventName = 'gaze';
const port = 8001;
let sock;
let surfaceOrigin, surfaceSize;

export const init = () => {
    updateDeviceStatus(deviceName, 'connecting...');
    sock = io.connect(`http://localhost:${port}`, { transports: ['websocket'] });  // TODO: https?
    sock.on('connect', () => {
        updateDeviceStatus(deviceName, 'connected');
        console.log(`${deviceName} server connected`);
    });
    sock.on('disconnect', () => {
        updateDeviceStatus(deviceName, 'disconnected');
        console.log(`${deviceName} server disconnected`);
    });
    sock.on('reconnect_attempt', () => {  // TODO: not working
        updateDeviceStatus(deviceName, 'reconnecting...');
        console.log(`${deviceName} server reconnecting...`);
    });
    sock.on(eventName, ({ x, y }) => {
        const mappedGaze = mapGazeToSurface(x, y);
        updateCursorAndFocus(...mappedGaze);
    });
    showAprilTags();
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

const mapGazeToSurface = (x, y) => {
    // [x, y] in the range of [0, 1]^2
    return [
        surfaceOrigin[0] + surfaceSize[0] * x,
        surfaceOrigin[1] + surfaceSize[1] * y,
    ];
}
