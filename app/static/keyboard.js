import { updateDeviceStatus } from './utils.js';

export const init = (commandHandler, commandLabels, userId, expId) => {
    // set key map
    // cancel: 0, others: 1, 2, ...
    const keyMap = {};
    if (commandLabels.includes('cancel')) keyMap['0'] = 'cancel';
    commandLabels.filter(label => label !== 'cancel').forEach((label, idx) => {
        keyMap[(idx + 1).toString()] = label;
    });

    const onKeydown = (event) => commandHandler(keyMap[event.key]);
    document.addEventListener('keydown', onKeydown);
    updateDeviceStatus('Keyboard', 'connected');
}
