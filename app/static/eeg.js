import { updateConnectionStatusElement } from './utils.js';

let sockEEG;

export const onToggleEEG = (checked, commandHandler, commandLabels) => {
    if (checked) {
        updateConnectionStatusElement('connecting', 'toggle-eeg');
        sockEEG = io.connect(`http://localhost:8002`, { transports: ['websocket'] });
        sockEEG.on('connect', () => {
            sockEEG.emit('init', { numClasses: commandLabels.length });
            updateConnectionStatusElement('connected', 'toggle-eeg');
            console.log("EEG server connected");
        });
        sockEEG.on('disconnect', () => {
            updateConnectionStatusElement('disconnected', 'toggle-eeg');
            console.log("EEG server disconnected");
        });
        sockEEG.on('reconnect_attempt', () => {  // TODO: not working
            console.log("EEG server reconnecting...");
        });
        sockEEG.on('ping', (ack) => ack());
        sockEEG.on('getTime', (ack) => ack(Date.now()));
        sockEEG.on('eeg', ({ cls, likelihoods }) => commandHandler(cls, likelihoods));
    } else {
        if (sockEEG) sockEEG.disconnect();
    }
}

export const sendDataCollectionOnset = (event) => {
    if (sockEEG) sockEEG.emit('dataCollectionOnset', event.detail);
}