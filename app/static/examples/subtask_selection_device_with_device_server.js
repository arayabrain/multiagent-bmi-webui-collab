// This is a template of how to add your custom subtask selection device which has a device server.
// See eeg.js for an actual example.

import { updateDeviceStatus } from '../utils.js';

const deviceName = 'Your Device';  // TODO: change this to the device name
const eventName = 'your_device';  // TODO: change this to the websocket event name from your device server
const port = 1234;  // TODO: change this to the port number of your device server
let sock;

export const init = (commandHandler, commandLabels, userId, expId) => {
    // connect to your device server
    updateDeviceStatus(deviceName, 'connecting...');
    sock = io.connect(`http://localhost:${port}`, { transports: ['websocket'] });

    // add websocket event handlers
    sock.on('connect', () => {
        // send init event to device
        sock.emit('init', {
            commandLabels: commandLabels,
            userId: userId,
            expId: expId,
        });
        // update device status display on browser
        updateDeviceStatus(deviceName, 'connected');
        console.log(`${deviceName} server connected`);
    });
    sock.on('disconnect', () => {
        updateDeviceStatus(deviceName, 'disconnected');
        console.log(`${deviceName} server disconnected`);
    });
    sock.on(eventName, ({ classId, likelihoods }) => {
        // send command to command handler (onSubtaskSelectionEvent in app.js)
        commandHandler(classId, likelihoods);
    });
}