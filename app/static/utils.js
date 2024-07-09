export const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

const deviceStatus = {};
export const updateDeviceStatus = (name, status) => {
    deviceStatus[name] = status;

    let statusText = '';
    for (const [name, status] of Object.entries(deviceStatus)) {
        statusText += `${name}: ${status}<br>`;
    }
    document.getElementById("device-status-area").innerHTML = statusText;
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

/* Helpers for tracking connected browsers server-side */
export const getCookie = (name) => {
    const cookieString = document.cookie;
    const cookies = cookieString.split('; ');

    for (let cookie of cookies) {
        const [key, value] = cookie.split('=');
        if (key === name) {
            return decodeURIComponent(value);
        }
    }
    return null;
};

export const disconnectUser = async (unique_user_id) => {
    console.log(JSON.stringify({"unique_user_id": unique_user_id}));
    // Helper to disconnect a user at the backend side
    const response = await fetch('/api/disconnect-user', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        // TODO: what if no unique_user_id ?
        body: JSON.stringify({unique_user_id: `${unique_user_id}`})
    });

    return response;
};
