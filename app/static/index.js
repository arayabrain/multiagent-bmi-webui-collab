document.addEventListener('DOMContentLoaded', async () => {
    document.querySelector('#userinfoForm').addEventListener('input', saveUserinfo);
    initUserinfo();

    document.querySelectorAll('.togglable').forEach(
        input => input.addEventListener('change', saveDeviceSelection)
    );
    initDeviceSelection();

    const modeLinks = document.querySelectorAll('.mode-link');
    modeLinks.forEach(link => {
        link.addEventListener('click', (event) => {
            // validate the user info
            const userinfo = JSON.parse(sessionStorage.getItem('userinfo'));
            const isUserinfoSet = userinfo && userinfo.name && userinfo.age && userinfo.gender;
            // validate the device selection
            const deviceSelection = JSON.parse(sessionStorage.getItem('deviceSelection'));
            const isDeviceSelected = deviceSelection && Object.values(deviceSelection).some(device => device);  // TODO: validate robot selection and subtask selection respectively
            if (!isUserinfoSet || !isDeviceSelected) {
                event.preventDefault();
                alert('Please set the user info and device selection before proceeding.');
            }
        });
    });
});


const saveUserinfo = () => {
    const userinfo = {
        name: document.querySelector('input[name="name"]').value,
        age: document.querySelector('input[name="age"]').value,
        gender: document.querySelector('select[name="gender"]').value,
    };
    sessionStorage.setItem('userinfo', JSON.stringify(userinfo));
}

const initUserinfo = () => {
    // if previous one exists, use it, otherwise save the default
    const userinfo = JSON.parse(sessionStorage.getItem('userinfo'));
    if (!userinfo) {
        saveUserinfo();
        return;
    }
    document.querySelector('input[name="name"]').value = userinfo.name;
    document.querySelector('input[name="age"]').value = userinfo.age;
    document.querySelector('select[name="gender"]').value = userinfo.gender;
}

const saveDeviceSelection = () => {
    // save the device state
    const state = {
        mouse: document.getElementById('toggle-mouse').checked,
        keyboard: document.getElementById('toggle-keyboard').checked,
        gamepad: document.getElementById('toggle-gamepad').checked,
        eeg: document.getElementById('toggle-eeg').checked,
        gaze: document.getElementById('toggle-gaze').checked,
    };
    sessionStorage.setItem('deviceSelection', JSON.stringify(state));
}

const initDeviceSelection = () => {
    // if previous one exists, use it, otherwise save the default
    const state = JSON.parse(sessionStorage.getItem('deviceSelection'));
    if (!state) {
        saveDeviceSelection();
        return;
    }
    // set the state
    document.getElementById('toggle-mouse').checked = state.mouse;
    document.getElementById('toggle-keyboard').checked = state.keyboard;
    document.getElementById('toggle-gamepad').checked = state.gamepad;
    document.getElementById('toggle-eeg').checked = state.eeg;
    document.getElementById('toggle-gaze').checked = state.gaze;
}

