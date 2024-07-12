const INDEX_LOCALIZATION = {
  "en": {
      // Headers
      "select-field-text": "Select Devices",
      "select-mode-text": "Select a Mode",
      "robot-selection-text": "Robot",
      "subtask-selection-text": "Robot",
      // Devices
      "toggle-mouse-text": "Mouse",
      "toggle-gamepad-0-text": "Gamepad",
      "toggle-gaze-text": "Eye Tracker",
      "toggle-keyboard-text": "Keyboard",
      "toggle-gamepad-1-text": "Gamepad",
      "toggle-eeg-text": "EEG/EMG",
      // Buttons
      "reset-user-btn-text": "Reset User",
      // Labels
      "ui-language-text": "Language"
  },
  "jp": {
      // Headers
      "select-field-text": "デバイス選択",
      "select-mode-text": "モード選択",
      "robot-selection-text": "ロボット",
      "subtask-selection-text": "サブタスク",
      // Devices
      "toggle-mouse-text": "マウス",
      "toggle-gamepad-0-text": "ゲームパッド",
      "toggle-gaze-text": "Eye Tracker",
      "toggle-keyboard-text": "キーボード",
      "toggle-gamepad-1-text": "ゲームパッド",
      "toggle-eeg-text": "EEG/EMG",
      // Buttons
      "reset-user-btn-text": "再設定",
      // Labels
      "ui-language-text": "言語"
  }
};

const REGISTER_LOCALIZATION = {
  "en": {
    // Headers
    "select-field-text": "Select Devices",
  },
  "jp": {
    // Headers
    "select-field-text": "デバイス選択",
  }
};

export const applyLocalization = (mode) => {
  // This fn will iterate over all fields specified for localization
  // and update the text to match the UILanguage that is set

  // TODO: don't update if the current localizatin is already correct
  var LOCALIZATION_DICT = INDEX_LOCALIZATION; // Index page by default
  // TODO: switch case for different modes to change LOCALIZATION_DICT
  switch(mode) {
    case "register":
      LOCALIZATION_DICT = REGISTER_LOCALIZATION;
      break;
    case "nasa-survey-tlx":
      console.log("Not implemented yet");
      break;
  }
  const UILanguage = sessionStorage.getItem("UILanguage");
  Object.entries(LOCALIZATION_DICT[UILanguage]).forEach(([fieldID, localizedFieldText]) => {
      document.getElementById(fieldID).textContent = localizedFieldText;
  });
};

export const initUILanguage = () => {
  // Read previous UI language value from session
  var UILanguage = sessionStorage.getItem("UILanguage");
  // If not in sessionStorage,read the default from the webpage
  if (!UILanguage) {
      UILanguage = document.getElementById('ui-language').value;
  } else {
      // Override webpage control with the previous value
      document.getElementById('ui-language').value = UILanguage;
  };
  // Update the UI based on the selected langauge if needs be
  applyLocalization();

  return UILanguage;
};