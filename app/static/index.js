import { disconnectUser, getCookie } from './utils.js';

// Tracking active tabs / window
let active_tab_detected = false;

if (localStorage.getItem("active-tab")) {
    active_tab_detected = true; // Closing this tab will not remove main tab(windows)'s "active-tab" flag
    const modal = document.getElementById('active-tab-modal');
    const modalInstance = new bootstrap.Modal(modal);
    modalInstance.show();
} else {
    localStorage.setItem("active-tab", true);
};

// Notify backend when the browser window is closed
// for server-side tracking of connected users
window.addEventListener("beforeunload", (event) => {
    // TODO: what if there is no unique_user_id set yet ?
    let unique_user_id = getCookie("unique_user_id");
    if (! active_tab_detected) {
        // Don't disconnect if another tab is opened, since main tab is still live
        disconnectUser(unique_user_id);
        // Negate active tab flag only if the current one is a valid one
        localStorage.removeItem("active-tab");
    };
});

window.addEventListener("unload", (event) => {
    let unique_user_id = getCookie("unique_user_id");
    if (! active_tab_detected) {
        // Don't disconnect if another tab is opened, since main tab is still live
        disconnectUser(unique_user_id);
        // Negate active tab flag only if the current one is a valid one
        localStorage.removeItem("active-tab");
    };
});


document.addEventListener('DOMContentLoaded', async () => {
    displayUserInfo();
    document.getElementById('resetUserInfo').addEventListener('click', () => {
        window.location.href = '/register';
    });

    document.querySelectorAll('.form-check-input').forEach(
        input => input.addEventListener('change', saveDeviceSelection)
    );
    initDeviceSelection();

    // Sync gamepad toggles for robot and subtask selection
    const gamepadCheckbox0 = document.getElementById('toggle-gamepad-0');
    const gamepadCheckbox1 = document.getElementById('toggle-gamepad-1');
    function syncCheckboxes(sourceCheckbox, targetCheckbox) {
        targetCheckbox.checked = sourceCheckbox.checked;
    };
    gamepadCheckbox0.addEventListener('change', () => {
        syncCheckboxes(gamepadCheckbox0, gamepadCheckbox1);
    });
    gamepadCheckbox1.addEventListener('change', () => {
        syncCheckboxes(gamepadCheckbox1, gamepadCheckbox0);
    });

    const modeLinks = document.querySelectorAll('.mode-link');
    modeLinks.forEach(link => {
        link.addEventListener('click', (event) => {
            // validate the device selection
            const deviceSelection = JSON.parse(sessionStorage.getItem('deviceSelection'));
            const isRobotDeviceSelected = document.getElementById(`toggle-mouse`).checked || document.getElementById(`toggle-gamepad-0`).checked || document.getElementById(`toggle-gaze`).checked;
            const isSubtaskDeviceSelected = document.getElementById(`toggle-keyboard`).checked || document.getElementById(`toggle-gamepad-1`).checked || document.getElementById(`toggle-eeg`).checked;
            const isDeviceSelected = deviceSelection && isRobotDeviceSelected && isSubtaskDeviceSelected
            console.log(`deviceSelection: ${deviceSelection}`);
            console.log(`isRobotDeviceSelected: ${isRobotDeviceSelected}`);
            console.log(`isSubtaskDeviceSelected: ${isSubtaskDeviceSelected}`);
            console.log(`IsDeviceSelected: ${isDeviceSelected}`);
            // TODO: validate robot selection and subtask selection respectively
            if (!isDeviceSelected) {
                event.preventDefault();
                alert('Please choose one device each from left & right column.');
            };
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
    const state = {};
    document.querySelectorAll('.form-check-input').forEach(input => {
        // NOTE: need to skip "toggle-gamepad-1" otherwise device selection
        // saving does not work
        if (input.id !== "toggle-gamepad-1") {
            const device = input.id.split('-')[1];
            state[device] = input.checked;
        };
    });
    sessionStorage.setItem('deviceSelection', JSON.stringify(state));
}

const initDeviceSelection = () => {
    // if previous one exists, use it, otherwise save the default
    const state = JSON.parse(sessionStorage.getItem('deviceSelection'));
    if (!state) return;

    // set the state
    Object.keys(state).forEach(device => {
        if (device == "gamepad") {
            // Special case
            document.getElementById(`toggle-${device}-0`).checked = state[device];
            document.getElementById(`toggle-${device}-1`).checked = state[device];
        } else {
            document.getElementById(`toggle-${device}`).checked = state[device];
        }
    });
}
