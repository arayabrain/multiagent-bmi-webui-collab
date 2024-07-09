import { disconnectUser, getCookie } from './utils.js';

// Notify backend when the browser window is closed
// for server-side tracking of connected users
window.addEventListener("beforeunload", (event) => {
    // TODO: what if there is no uniquer_user_id set yet ?
    let unique_user_id = getCookie("unique_user_id");
    console.log(unique_user_id);
    disconnectUser(unique_user_id);
});

window.addEventListener("unload", (event) => {
    let unique_user_id = getCookie("unique_user_id");
    console.log(unique_user_id);
    disconnectUser(unique_user_id);
});


document.addEventListener('DOMContentLoaded', () => {
    document.querySelector('#userinfoForm').addEventListener('submit', async event => {
        event.preventDefault();
        await saveUserinfo();
    });
    document.querySelector('#clearButton').addEventListener('click', clearForm);
    initUserinfo();
});


const saveUserinfo = async () => {
    const userinfo = {
        projectName: document.querySelector('input[name="projectName"]').value,
        name: document.querySelector('input[name="name"]').value,
        age: document.querySelector('input[name="age"]').value,
        gender: document.querySelector('select[name="gender"]').value,
        handedness: document.querySelector('input[name="handedness"]:checked').value,
    };

    const response = await fetch('/api/setuser', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(userinfo)
    });

    if (response.status == 400) {
        // NOTE: for now, the only type of error we get
        // at this point is if the user is already registered
        // Rigorously, we would iterate over all errors in thel ist
        // and affect the corresponding field appropriately.
        let usernameFormFiled = document.getElementById("name");
        usernameFormFiled.classList.add("is-invalid");
    };

    if (response.ok) {
        window.location.href = '/';  // Redirect to the index page
    };
}

const initUserinfo = async () => {
    // if previous one exists, use it, otherwise save the default
    const response = await fetch('/api/getuser');
    const userinfo = await response.json();
    if (!userinfo) return;

    document.querySelector('input[name="projectName"]').value = userinfo.projectName;
    document.querySelector('input[name="name"]').value = userinfo.name;
    document.querySelector('input[name="age"]').value = userinfo.age;
    document.querySelector('select[name="gender"]').value = userinfo.gender;
    document.querySelector(`input[name="handedness"][value="${userinfo.handedness}"]`).checked = true;
}

const clearForm = () => {
    document.querySelector('input[name="projectName"]').value = 'hri-benchmark';
    document.querySelector('input[name="name"]').value = '';
    document.querySelector('input[name="age"]').value = '';
    document.querySelector('select[name="gender"]').value = '';
    document.querySelector('input[name="handedness"][value="right"]').checked = true;
}


