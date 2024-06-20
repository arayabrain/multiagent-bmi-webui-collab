import { updateDeviceStatus } from './utils.js';

const NASATLXFieldToInputName = {
  "mental-demand": "mentalDemandOptions",
  "physical-demand": "physicalDemandOptions",
  "temporal-demand": "temporalDemandOptions",
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
  document.querySelector('#rndfill-button').addEventListener('click', randomFormFill);

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

// For debug purposes, randomly fill the form before sending data
const randomFormFill = () => {

  Object.keys(NASATLXFieldToInputName).forEach(key => {
    // Get collection of radio buttons
    const radioButtons = document.getElementsByName(NASATLXFieldToInputName[key]);
    // Uncheck radio buttons of each field.
    let valueToCheck = Math.floor(Math.random() * (7) + 1);

    radioButtons.forEach(radio => {
      if (parseInt(radio.value, 10) == valueToCheck) {
        radio.checked = true;
      }
    });
  });
}

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
    const inputValue = document.querySelector(`input[name="${inputName}"]:checked`);
    NASATLXSurveyData[key] = null; // Placeholder value

    if (inputValue) {
      NASATLXSurveyData[key] = parseInt(inputValue.value, 10);
    } else {
      nullKeyFound = true;
    }
  }
  console.log(NASATLXSurveyData);

  // Assert that there is not null key
  if (nullKeyFound) {
    // TODO: cleaner / integrate way of notifiying use
    // by using a modal for e.g. ?
    alert("All fields are required");
    return false;
  }

  // Add userinfo and device selection
  NASATLXSurveyData["device-selection"] = JSON.parse(sessionStorage.getItem("deviceSelection"));
  NASATLXSurveyData["userinfo"] = JSON.parse(sessionStorage.getItem("userinfo"));

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