document.addEventListener('DOMContentLoaded', async () => {
    document.querySelectorAll('.togglable').forEach(
        input => input.addEventListener('change', saveDeviceSelection)
    );
    initDeviceSelectionToggles();

    // check if the user info is already set
    const res = await fetch('/api/getuser');
    const userinfo = await res.json();
    if (userinfo) {
        onUserinfoAccepted(userinfo);
    }

    // set the user info
    document.getElementById('usernameForm').addEventListener('submit', async (event) => {
        event.preventDefault();  // prevent the form from submitting
        const formData = new FormData(document.getElementById('usernameForm'));
        const res = await fetch('/api/setuser', {
            method: 'POST',
            body: formData,
        });
        const userinfo = await res.json();
        if (res.ok) {
            onUserinfoAccepted(userinfo);
        } else {
            showError(userinfo.detail);
        }
    });

    // reset button
    document.getElementById('resetButton').addEventListener('click', resetForm);
});

const showError = (errMsg) => {
    // show the error message
    const resultArea = document.getElementById('resultArea');
    resultArea.style.display = 'block';
    resultArea.innerHTML = errMsg;
}

const onUserinfoAccepted = (userinfo) => {
    // hide the form
    const usernameForm = document.getElementById('usernameForm');
    usernameForm.style.display = 'none';
    // show the user info
    const resultArea = document.getElementById('resultArea');
    resultArea.style.display = 'block';
    resultArea.innerHTML = `
        <div class="info-row mb-2 d-flex align-items-center"><span class="info-label fw-bold text-end pe-3" style="width: 120px;">Username:</span><span class="info-value">${userinfo.username}</span></div>
        <div class="info-row mb-2 d-flex align-items-center"><span class="info-label fw-bold text-end pe-3" style="width: 120px;">Age:</span><span class="info-value">${userinfo.age}</span></div>
        <div class="info-row mb-2 d-flex align-items-center"><span class="info-label fw-bold text-end pe-3" style="width: 120px;">Gender:</span><span class="info-value">${userinfo.gender}</span></div>
    `;
    // show the reset button
    const resetButton = document.getElementById('resetButton');
    resetButton.style.display = 'block';
    // show the environment links
    const envElements = document.querySelectorAll('.hidden-before-submit');
    envElements.forEach(el => el.style.display = 'flex');
}

const resetForm = async () => {
    const res = await fetch('/api/resetuser', {
        method: 'POST',
    });
    const data = await res.json();
    if (data.success) {
        // show the form
        const usernameForm = document.getElementById('usernameForm');
        usernameForm.style.display = 'block';
        usernameForm.reset();
        // hide the user info
        const resultArea = document.getElementById('resultArea');
        resultArea.style.display = 'none';
        resultArea.innerHTML = '';
        // hide the reset button
        const resetButton = document.getElementById('resetButton');
        resetButton.style.display = 'none';
        // hide the environment links
        const envElements = document.querySelectorAll('.hidden-before-submit');
        envElements.forEach(el => el.style.display = 'none');
    } else {
        showError('Failed to reset user info');
    }
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

const initDeviceSelectionToggles = () => {
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

