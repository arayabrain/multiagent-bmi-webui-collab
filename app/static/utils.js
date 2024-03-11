export const updateConnectionStatusElement = (status, statusElementId) => {
    var statusElement = document.getElementById(statusElementId);
    statusElement.classList.remove('connected', 'disconnected', 'connecting');
    switch (status) {
        case 'connected':
            statusElement.classList.add('connected');
            break;
        case 'disconnected':
            statusElement.classList.add('disconnected');
            break;
        case 'connecting':
            statusElement.classList.add('connecting');
            break;
        default:
            console.error("Unknown status: ", status);
    }
}

export const binStr2Rgba = (str, alpha = 0.3) => {
    // input should be like '010'
    if (str.length !== 3 || !/^[01]{3}$/.test(str)) {
        throw new Error('Invalid input');
    }
    const red = parseInt(str.charAt(0), 10) * 255;
    const green = parseInt(str.charAt(1), 10) * 255;
    const blue = parseInt(str.charAt(2), 10) * 255;
    return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

export const scaleRgba = (rgba, scale, alpha = null) => {
    const [red, green, blue, _alpha] = rgba.match(/\d+/g);
    if (alpha === null) alpha = _alpha;
    return `rgba(${Math.floor(red * scale)}, ${Math.floor(green * scale)}, ${Math.floor(blue * scale)}, ${alpha})`;
}
