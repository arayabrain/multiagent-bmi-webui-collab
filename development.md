# Development

## Add a new device
"your_device" is a placeholder for the name of the new device.

### Create initialization functions to communicate with the device

#### If the browser can directly read device input
- Add a script for the browser to process device input
    - `app/static/your_device.js`
    - This script exports a function `init` that adds a handler for the browser to receive device input, such as event listeners or polling loops.
    - For robot selection device (e.g., mouse)
        - `init` takes no arguments.
        - Use `updateCursorAndFocus` function to update the cursor position and robot selection.
        - For an actual example, refer to [mouse.js](app/static/mouse.js)
    - For subtask selection device (e.g., keyboard)
        - `init` takes four arguments:
            - `commandHandler`: a function that handles the command (`onSubtaskSelectionEvent(command, likelihoods = undefined)` defined in [app.js](app/static/app.js))
            - `commandLabels`: a list of command labels
            - `userId`: user ID
            - `expId`: experiment ID
        - Use `commandHandler` to send the subatask selection command to the server.
        - For an actual example, refer to [keyboard.js](app/static/keyboard.js)

#### If the browser cannot directly read device input
- Create a "device server"
    - `app/devices/your_device/main.py`
    - This script launches a server that receives input from the device and sends it to the browser via websocket.
    - Template: [app/devices/example/main.py](app/devices/example/main.py)
    - For robot selection device (e.g., gaze)
        - Receive signals from the device, decode them to cursor coordinates, and send them to the browser via websocket.
        - For an actual example, refer to [eye/main.py](app/devices/eye/main.py)
    - For subtask selection device (e.g., EEG)
        - Receive signals from the device, decode them to commands and likelihoods, and send them to the browser via websocket.
        - For an actual example, refer to [eeg/main.py](app/devices/eeg/main.py)
- Add a script for the browser to communicate with the device server
    - `app/static/your_device.js`
    - This script exports a function `init` that creates a websocket connection to the device server.
    - For robot selection device (e.g., gaze)
        - `init` takes no arguments.
        - Use `updateCursorAndFocus` function to update the cursor position and robot selection.
        - For an actual example, refer to [gaze.js](app/static/gaze.js)
        - Template: [robot_selection_device_with_device_server.js](app/static/examples/robot_selection_device_with_device_server.js)
    - For subtask selection device (e.g., EEG)
        - `init` takes four arguments:
            - `commandHandler`: a function that handles the command (`onSubtaskSelectionEvent(command, likelihoods = undefined)` defined in [app.js](app/static/app.js))
            - `commandLabels`: a list of command labels
            - `userId`: user ID
            - `expId`: experiment ID
        - Use `commandHandler` to send the subatask selection command to the server.
        - For an actual example, refer to [eeg.js](app/static/eeg.js)
        - Template: [subtask_selection_device_with_device_server.js](app/static/examples/subtask_selection_device_with_device_server.js)
    - Import the `init` function in `app/static/app.js` in the same way as above.

#### Import the `init` function
- In `app/static/app.js`:
    ```js
    import { init as initYourDevice } from './your_device.js';
    const robotSelectionDeviceInitFuncs = {
        mouse: initMouse,
        gaze: initGaze,
        yourDevice: initYourDevice,  // if it is a robot selection device, add here
    };
    const subtaskSelectionDeviceInitFuncs = {
        keyboard: initKeyboard,
        gamepad: initGamepad,
        eeg: initEEG,
        yourDevice: initYourDevice,  // if it is a subtask selection device, add here
    };
    ```

### Add a switch for device selection
- Here, add a device selection switch to the index page.
    ![index page](assets/index_page.png){ height=320 }
- In `app/templates/index.html`:
    ```html
    <div class="form-check form-switch">
        <input class="form-check-input" type="checkbox" id="toggle-${device_name}">
        <label class="form-check-label" for="toggle-${device_name}">${device_name}</label>
    </div>
    ```

