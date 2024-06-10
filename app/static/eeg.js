import { updateDeviceStatus } from './utils.js';

const deviceName = 'EEG/EMG';
const eventName = 'eeg';
const port = 8002;
let sock;

export const init = (commandHandler, commandLabels, userId, expId) => {
    updateDeviceStatus(deviceName, 'connecting...');
    sock = io.connect(`http://localhost:${port}`, { transports: ['websocket'] });

    sock.on('connect', () => {
        sock.emit('init', {
            commandLabels: commandLabels,
            userId: userId,
            expId: expId,
        });
        updateDeviceStatus(deviceName, 'connected');
        console.log("EEG server connected");
    });
    sock.on('disconnect', () => {
        updateDeviceStatus(deviceName, 'disconnected');
        console.log("EEG server disconnected");
    });
    sock.on('reconnect_attempt', () => {  // TODO: not working
        updateDeviceStatus(deviceName, 'reconnecting...');
        console.log("EEG server reconnecting...");
    });
    sock.on(eventName, ({ classId, likelihoods }) => commandHandler(classId, likelihoods));
    sock.on('ping', (ack) => ack());
    sock.on('getTime', (ack) => ack(Date.now()));
}

export const sendDataCollectionOnset = (event) => {
    if (sock) sock.emit('dataCollectionOnset', event.detail);
}