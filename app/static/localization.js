// Localization text for components "shared across pages", not langagues
const SHARED_LOCALIZATION = {
  "en": {
    // Modals
    "activeTabModalLabel": "Running session detected in another tab or window ! Please close this one.",
    "taskCompleteModalLabel": "Task Complete !"
  },
  "jp": {
    // Modals
    "activeTabModalLabel": "他のタブまたウィンドウでログインされている．このタブを閉じてください．",
    "taskCompleteModalLabel": "完了！"
  }
}

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
    "ui-language-text": "Language",
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
    "ui-language-text": "Language",
  }
};

const REGISTER_LOCALIZATION = {
  "en": {
    // Headers
    "enter-userinfo-text": "Enter User Information",

    // Buttons
    "registerButton": "Register",
    "clearButton": "Clear",

    // Labels
    "gender-select-text": "Select Gender",
    "gender-male-text": "Male",
    "gender-female-text": "Female",
    "leftHand-text": "Left-handed",
    "rightHand-text": "Right-handed",
    "ui-language-text": "Language | 言語",

    // Form feedback
    "invalid-username-feedback-text": "A user with the same username is already connected.",
    // Inputs placeholders // TODO: better way to handle this.
    // A naive idea is to set the DOM element name to "register-<name>"
    // then have applyLocalization make an exception for those felds and set the 
    // placeholder attribute instead of textContent.
    // "name": "Enter your name",
    // "age": "Enter your age",
    // "projectName": "Project name",
  },
  "jp": {
    // Headers
    "enter-userinfo-text": "ユーザー登録", // TODO: JP check

    // Buttons
    "registerButton": "登録",
    "clearButton": "クリアー",

    // Labels
    "gender-select-text": "性別の選択",
    "gender-male-text": "男性",
    "gender-female-text": "女性",
    "leftHand-text": "左利き",
    "rightHand-text": "右利き",
    "ui-language-text": "Language | 言語",

    // Form feedback
    "invalid-username-feedback-text": "入力した名前は他ユーザーに利用されている．",
    // Inputs placeholders // TODO: better way to handle this.
    // "name": "名前を入力",
    // "age": "年齢を入力",
    // "projectName": "プロジェクト名を入力",
  }
};

const NASA_TLX_LOCALIZATION = {
  "en": {
    // Field legends
    "mentalDemand-legend-text": "Mental Demand",
    "physicalDemand-legend-text": "Physical Demand",
    "temporalDemand-legend-text": "Temporal Demand",
    "performance-legend-text": "Performance",
    "effort-legend-text": "Effort",
    "frustration-legend-text": "Mental",

    // Field descriptions
    "mentalDemand-description-text": "How mentally demanding was the task ?",
    "physicalDemand-description-text": "How physically demanding was the task ?",
    "temporalDemand-description-text": "How hurried or rushed was the pace of the task ?",
    "performance-description-text": "How successful were you in accomplishing what you were asked to do ?",
    "effort-description-text": "How hard did you have to work to accomplish your level of performance ?",
    "frustration-description-text": "How insecure, discouraged, irritated, stressed, and annoyed were you ?",

    // Input labels
    // // Very low labels values
    "mentalDemand-low-label": "Very Low",
    "physicalDemand-low-label": "Very Low",
    "temporalDemand-low-label": "Very Low",
    "performance-low-label": "Perfect",
    "effort-low-label": "Very Low",
    "frustration-low-label": "Very Low",
    // // Very High labels values
    "mentalDemand-high-label": "Very High",
    "physicalDemand-high-label": "Very High",
    "temporalDemand-high-label": "Very High",
    "performance-high-label": "Failure",
    "effort-high-label": "Very High",
    "frustration-high-label": "Very High",

    // Buttons
    "clear-button": "Clear",
    "submit-button": "Submit",
  },
  "jp": {
    // Field legends
    "mentalDemand-legend-text": "精神的負担",
    "physicalDemand-legend-text": "身体的負担",
    "temporalDemand-legend-text": "時間的負担",
    "performance-legend-text": "性能",
    "effort-legend-text": "努力",
    "frustration-legend-text": "ストレス",

    // Field descriptions
    "mentalDemand-description-text": "この課題はどの程度精神的に負担でしたか？",
    "physicalDemand-description-text": "この課題はどの程度身体的に負担でしたか？",
    "temporalDemand-description-text": "この課題のペースはどの程度急かされましたか？",
    "performance-description-text": "求められたことをどの程度達成できましたか？",
    "effort-description-text": "パフォーマンスを達成するためにどの程度努力しましたか？",
    "frustration-description-text": "どの程度不安、落胆、苛立ち、ストレス、イライラを感じましたか？",

    // Input labels
    // // Very low labels values
    "mentalDemand-low-label": "最低",
    "physicalDemand-low-label": "最低",
    "temporalDemand-low-label": "最低",
    "performance-low-label": "完璧",
    "effort-low-label": "最低",
    "frustration-low-label": "最低",
    // // Very High labels values
    "mentalDemand-high-label": "最高",
    "physicalDemand-high-label": "最高",
    "temporalDemand-high-label": "最高",
    "performance-high-label": "失敗",
    "effort-high-label": "最高",
    "frustration-high-label": "最高",

    // Buttons
    "clear-button": "クリアー",
    "submit-button": "送信",
  }
};

// TODO or not TODO, that is the question ...
const APP_LOCALIZATION = {
  "en": {},
  "jp": {}
};


export const applyLocalization = (mode) => {
  // This fn will iterate over all fields specified for localization
  // and update the text to match the UILanguage that is set
  // console.log(`Running local. for ${mode}`); // DBG
  // TODO: don't update if the current localizatin is already correct
  var LOCALIZATION_DICT = INDEX_LOCALIZATION; // Index page by default
  // TODO: switch case for different modes to change LOCALIZATION_DICT
  switch(mode) {
    case "shared":
      LOCALIZATION_DICT = SHARED_LOCALIZATION;
      break;
    case "register":
      LOCALIZATION_DICT = REGISTER_LOCALIZATION;
      break;
    case "app":
      LOCALIZATION_DICT = APP_LOCALIZATION;
      break
    case "nasa-tlx-survey":
      LOCALIZATION_DICT = NASA_TLX_LOCALIZATION;
      break;
  };

  var UILanguage = sessionStorage.getItem("UILanguage");
  if (UILanguage === null) {
    UILanguage = "en"; // Use English by default, i.e. fresh session
  };
  Object.entries(LOCALIZATION_DICT[UILanguage]).forEach(([fieldID, localizedFieldText]) => {
    try {
      // console.log(`Attempting local. of ${fieldID}`); // DBG
      document.getElementById(fieldID).textContent = localizedFieldText;
    } catch {
      console.log(`Issue localizing: ${fieldID}`);
    };
  });
};

export const initUILanguage = (mode) => {
  // Read UI language value from session
  var UILanguage = sessionStorage.getItem("UILanguage");

  if (mode == "index" || mode == "register") {
    // If not in sessionStorage,read the default from the webpage
    if (!UILanguage) {
      UILanguage = document.getElementById('ui-language').value;
    } else {
      // Override webpage control with the previous value
      document.getElementById('ui-language').value = UILanguage;
    };
  };
  // Update the UI based on the selected langauge if needs be
  applyLocalization(mode);

  return UILanguage;
};
