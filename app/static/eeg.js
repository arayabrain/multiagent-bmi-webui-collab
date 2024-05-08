import { updateDeviceStatus } from './utils.js';

let sockEEG;
const name = 'EEG/EMG';

export const initEEG = (commandHandler, commandLabels, userId, expId) => {
    updateDeviceStatus(name, 'connecting...');
    sockEEG = io.connect(`http://localhost:8002`, { transports: ['websocket'] });
    sockEEG.on('connect', () => {
        sockEEG.emit('init', {
            commandLabels: commandLabels,
            userId: userId,
            expId: expId,
        });
        updateDeviceStatus(name, 'connected');
        console.log("EEG server connected");
    });
    sockEEG.on('disconnect', () => {
        updateDeviceStatus(name, 'disconnected');
        console.log("EEG server disconnected");
    });
    sockEEG.on('reconnect_attempt', () => {  // TODO: not working
        updateDeviceStatus(name, 'reconnecting...');
        console.log("EEG server reconnecting...");
    });
    sockEEG.on('ping', (ack) => ack());
    sockEEG.on('getTime', (ack) => ack(Date.now()));
    sockEEG.on('eeg', ({ cls, likelihoods }) => commandHandler(cls, likelihoods));
}

export const sendDataCollectionOnset = (event) => {
    if (sockEEG) sockEEG.emit('dataCollectionOnset', event.detail);
}