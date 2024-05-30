// This is a template of how to add your custom robot selection device which has a device server.
// See gaze.js for an actual example.

import { updateDeviceStatus } from '../utils.js';
import { updateCursorAndFocus } from './cursor.js';

const port = 1234;  // TODO: change this to the port number of your device server
const deviceName = 'Your Device';  // TODO: change this to the device name
const eventName = 'your_device';  // TODO: change this to the websocket event name from your device server
let sock;

export const init = () => {
    // connect to your device server
    updateDeviceStatus(deviceName, 'connecting...');
    sock = io.connect(`http://localhost:${port}`, { transports: ['websocket'] });

    // add websocket event handlers
    sock.on('connect', () => {
        // update device status display on browser
        updateDeviceStatus(deviceName, 'connected');
        console.log(`${deviceName} server connected`);
    });
    sock.on('disconnect', () => {
        updateDeviceStatus(deviceName, 'disconnected');
        console.log(`${deviceName} server disconnected`);
    });
    sock.on(eventName, ({ x, y }) => {
        updateCursorAndFocus(...mapToWindow(x, y));
    });
}

const mapToWindow = (x, y) => {
    // map the device coordinates (x, y) to window coordinates...
    return [x, y];
}

