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
    // TODO: what if there is no uniquer_user_id set yet ?
    let unique_user_id = getCookie("unique_user_id");
    disconnectUser(unique_user_id);
    // Negate active tab flag only if the current one is a valid one
    if (! active_tab_detected) {
        localStorage.removeItem("active-tab");
    };
});

window.addEventListener("unload", (event) => {
    let unique_user_id = getCookie("unique_user_id");
    disconnectUser(unique_user_id);
    // Negate active tab flag only if the current one is a valid one
    if (! active_tab_detected) {
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

    const modeLinks = document.querySelectorAll('.mode-link');
    modeLinks.forEach(link => {
        link.addEventListener('click', (event) => {
            // validate the device selection
            const deviceSelection = JSON.parse(sessionStorage.getItem('deviceSelection'));
            const isRobotDeviceSelected = document.getElementById(`toggle-mouse`).checked || document.getElementById(`toggle-gamepad`).checked || document.getElementById(`toggle-gaze`).checked;
            const isSubtaskDeviceSelected = document.getElementById(`toggle-keyboard`).checked || document.getElementById(`toggle-eeg`).checked;
            const isDeviceSelected = deviceSelection && isRobotDeviceSelected && isSubtaskDeviceSelected
            // TODO: validate robot selection and subtask selection respectively            
            if (!isDeviceSelected) {
                event.preventDefault();
                alert('Please choose one device each from left & right column.');
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
    const state = {};
    document.querySelectorAll('.form-check-input').forEach(input => {
        const device = input.id.split('-')[1];
        state[device] = input.checked;
    });
    sessionStorage.setItem('deviceSelection', JSON.stringify(state));
}

const initDeviceSelection = () => {
    // if previous one exists, use it, otherwise save the default
    const state = JSON.parse(sessionStorage.getItem('deviceSelection'));
    if (!state) return;

    // set the state
    Object.keys(state).forEach(device => {
        document.getElementById(`toggle-${device}`).checked = state[device];
    });
}
