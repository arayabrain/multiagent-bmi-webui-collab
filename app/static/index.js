document.addEventListener('DOMContentLoaded', async () => {
    displayUserInfo();
    document.getElementById('resetUserInfo').addEventListener('click', () => {
        window.location.href = '/register';
    });

    document.querySelectorAll('.togglable').forEach(
        input => input.addEventListener('change', saveDeviceSelection)
    );
    initDeviceSelection();

    const modeLinks = document.querySelectorAll('.mode-link');
    modeLinks.forEach(link => {
        link.addEventListener('click', (event) => {
            // validate the device selection
            const deviceSelection = JSON.parse(sessionStorage.getItem('deviceSelection'));
            const isDeviceSelected = deviceSelection && Object.values(deviceSelection).some(device => device);
            // TODO: validate robot selection and subtask selection respectively
            if (!isDeviceSelected) {
                event.preventDefault();
                alert('Please set the user info and device selection before proceeding.');
            }
        });
    });
});

const displayUserInfo = async () => {
    const response = await fetch('/api/getuser');
    const userinfo = await response.json();
    if (!userinfo) {
        console.error('User info not found');
        return;
    }
    document.getElementById('displayUserInfo').textContent = `${userinfo.name}`;
};

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
