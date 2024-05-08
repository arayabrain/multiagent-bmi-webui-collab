import { updateCursorAndFocus } from './cursor.js';
import { updateDeviceStatus } from './utils.js';

const sampleRate = 60;  // Hz
const sensitivity = 40;
let _commandHandler, keyMap, prevPressed, intervalId = null;

export const setGamepadHandler = (commandHandler, commandLabels, userId, expId) => {
    _commandHandler = commandHandler;
    // set key map (for Xbox 360 controller)
    keyMap = {
        1: commandLabels[0],  // B
        0: commandLabels[1],  // A
        2: commandLabels[2],  // X
        3: commandLabels[3],  // Y
        8: 'cancel',  // Start
    };
    // initialize the state of button presses
    prevPressed = Object.fromEntries(Object.keys(keyMap).map(key => [key, false]));

    window.addEventListener("gamepadconnected", connect);
    window.addEventListener("gamepaddisconnected", disconnect);
}

const connect = (event) => {
    const gamepad = event.gamepad;
    console.log(
        "Gamepad connected at index %d: %s. %d buttons, %d axes.",
        gamepad.index, gamepad.id, gamepad.buttons.length, gamepad.axes.length
    );
    if (!intervalId) {
        intervalId = setInterval(gamepadsLoop, 1000 / sampleRate);
        updateDeviceStatus('Gamepad', 'connected');
    }
}

const disconnect = (event) => {
    const gamepad = event.gamepad;
    console.log(
        "Gamepad disconnected from index %d: %s",
        gamepad.index, gamepad.id
    );
    if (getActiveGamepadsCount() === 0) {
        clearInterval(intervalId);
        intervalId = null;
        updateDeviceStatus('Gamepad', 'disconnected');
    }
}

const getActiveGamepadsCount = () => {
    const gamepads = navigator.getGamepads();
    return gamepads.filter(gp => gp !== null).length;
}

const gamepadsLoop = () => {
    // get the first valid gamepad
    const gp = navigator.getGamepads().find(gp => gp !== null);
    if (gp === undefined) return;

    // move the cursor by joysticks
    let x, y;
    if (gp.axes.length == 2) {
        // one joystick
        x = gp.axes[0];
        y = gp.axes[1];
    } else if (gp.axes.length == 4) {
        // two joysticks
        // assume axes 0, 2 are for x and 1, 3 are for y
        // use the one with the largest magnitude
        x = Math.abs(gp.axes[0]) > Math.abs(gp.axes[2]) ? gp.axes[0] : gp.axes[2];
        y = Math.abs(gp.axes[1]) > Math.abs(gp.axes[3]) ? gp.axes[1] : gp.axes[3];
    } else {
        console.error("Unexpected number of axes: ", gp.axes.length);
        return;
    }
    // ignore small values to avoid cursor drift
    if (Math.abs(x) > 0.1 || Math.abs(y) > 0.1) {
        updateCursorAndFocus(x * sensitivity, y * sensitivity, true);
    }

    // subtask selection by buttons
    for (const key in keyMap) {
        if (gp.buttons[key].pressed && !prevPressed[key]) {
            _commandHandler(keyMap[key]);
            console.log("Button pressed: ", keyMap[key])
            break;  // only one command per frame
        }
    }
    // update the prev state
    Object.keys(keyMap).forEach((key) => {
        prevPressed[key] = gp.buttons[key].pressed;
    });
}

