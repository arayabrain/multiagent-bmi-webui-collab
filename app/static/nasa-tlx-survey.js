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


const NASATLXFieldToInputName = {
  "mentalDemand": "mentalDemandOptions",
  "physicalDemand": "physicalDemandOptions",
  "temporalDemand": "temporalDemandOptions",
  "performance": "performanceOptions",
  "effort": "effortOptions",
  "frustration": "frustrationOptions"
}

const deviceIDToPrettyName = {
  "mouse": "Mouse",
  "keyboard": "Keyboard",
  "gamepad": "Gamepad",
  "gaze": "Eye Tracker",
  "eeg": "EMG/EEG"
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelector('#nasa-tlx-survey-form').addEventListener('submit', async event => {
      event.preventDefault();
      await saveNASATLXSurveyData();
  });
  document.querySelector('#clear-button').addEventListener('click', clearForm);

  // Display the current user name
  document.getElementById("username-area").innerHTML = "User: " + JSON.parse(sessionStorage.userinfo).name;

  // Display the selected devices
  let connecteDevices = "Device(s) in use:";
  Object.entries(JSON.parse(sessionStorage.deviceSelection)).forEach(([deviceID, isUsed]) => {
    if (isUsed) {
      connecteDevices += " " + deviceIDToPrettyName[deviceID];
    };
  });
  document.getElementById("device-status-area").innerHTML = connecteDevices;
});

// Clears the form
const clearForm = () => {
  document.getElementById("nasa-tlx-survey-form").reset();
}

const saveNASATLXSurveyData = async () => {
  // Collect the survey data
  const NASATLXSurveyData = {}
  let nullKeyFound = false;

  for (const key of Object.keys(NASATLXFieldToInputName)) {
    const inputName = NASATLXFieldToInputName[key];
    const inputValue = document.querySelector(`input[name="${inputName}"]`);

    NASATLXSurveyData[key] = parseInt(inputValue.value, 10);
  }
  
  // Recover the mode
  // NOTE !!! The survey must be accessed from the modal, otherwise
  // this will fail, and there won't be info about what "mode" this
  // experiment data corresponds to.
  try {
    // If survey form is invoked without an experiment being done before
    // this allows us to still recover the results
    var previousURL = new URL(document.referrer);
    var mode = previousURL.pathname.split('/').filter(Boolean).pop();

    // Add userinfo and device selection
    NASATLXSurveyData["device-selection"] = JSON.parse(sessionStorage.getItem("deviceSelection"));
    NASATLXSurveyData["userinfo"] = JSON.parse(sessionStorage.getItem("userinfo"));
    NASATLXSurveyData["mode"] = mode;

    // Send the collected data to the Python backend for saving
    const response = await fetch("/api/save-nasa-tlx-data", {
      method: 'POST',
      headers: {
          'Content-Type': 'application/json'
      },
      body: JSON.stringify(NASATLXSurveyData)
    });

    if (response.ok) {
      window.location.href = '/';  // Redirect to the index page
    }
  }
  catch (e) {
    // In case previousURL query has failed, just print the survey results to console.log
    // as a fallback mechanism, then manually add that data to the survey folder.
    console.log(`Exception caught: ${e}`);
    console.log(JSON.stringify(NASATLXSurveyData));
  }
}
