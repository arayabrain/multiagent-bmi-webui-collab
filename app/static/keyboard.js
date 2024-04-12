export const onToggleKeyboard = (checked, commandHandler, commandLabels) => {
    // set key map
    // cancel: 0, others: 1, 2, ...
    const keyMap = {};
    if (commandLabels.includes('cancel')) keyMap['0'] = 'cancel';
    commandLabels.filter(label => label !== 'cancel').forEach((label, idx) => {
        keyMap[(idx + 1).toString()] = label;
    });

    const onKeydown = (event) => commandHandler(keyMap[event.key]);
    if (checked) {
        document.addEventListener('keydown', onKeydown);
    } else {
        document.removeEventListener('keydown', onKeydown);
    }
}
