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
    if (response.ok) {
        window.location.href = '/';  // Redirect to the index page
    }
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


