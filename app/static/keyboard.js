let keyMap;

export const onToggleKeyboard = (checked, commandHandler) => {
    const _onKeydown = (event) => onKeydown(event, commandHandler);
    if (checked) {
        document.addEventListener('keydown', _onKeydown);
    } else {
        document.removeEventListener('keydown', _onKeydown);
    }
}

const onKeydown = (event, commandHandler) => {
    if (keyMap === undefined || !keyMap.hasOwnProperty(event.key)) return;
    commandHandler(keyMap[event.key]);
}

export const setKeyMap = (commandLabels) => {
    keyMap = {};
    // cancel: 0, others: 1, 2, ...
    if (commandLabels.includes('cancel')) keyMap['0'] = 'cancel';
    commandLabels.filter(label => label !== 'cancel').forEach((label, idx) => {
        keyMap[(idx + 1).toString()] = label;
    });
}

