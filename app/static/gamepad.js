import { updateCursorAndFocus } from './cursor.js';

let animationFrameRequest;
const sensitivity = 60;

export const setGamepadHandler = () => {
    window.addEventListener("gamepadconnected", (event) => gamepadHandler(event, true));
    window.addEventListener("gamepaddisconnected", (event) => gamepadHandler(event, false));
}

const gamepadHandler = (event, connecting) => {
    const gamepad = event.gamepad;
    if (connecting) {
        console.log(
            "Gamepad connected at index %d: %s. %d buttons, %d axes.",
            gamepad.index, gamepad.id, gamepad.buttons.length, gamepad.axes.length
        );
        if (getActiveGamepadsCount() === 1) {
            document.getElementById('toggle-gamepad').checked = true;
            gamepadsLoop();  // start the loop
        }
    } else {
        console.log(
            "Gamepad disconnected from index %d: %s",
            gamepad.index, gamepad.id
        );
        if (getActiveGamepadsCount() === 0) {
            if (animationFrameRequest) cancelAnimationFrame(animationFrameRequest);  // stop the loop
            document.getElementById('toggle-gamepad').checked = false;
        }
    }
}

const getActiveGamepadsCount = () => {
    const gamepads = navigator.getGamepads();
    return gamepads.filter(gp => gp !== null).length;
}

const gamepadsLoop = () => {
    navigator.getGamepads().forEach((gp) => {
        if (gp === null) return;

        let gpX, gpY;
        if (gp.axes.length == 2) {
            gpX = gp.axes[0];
            gpY = gp.axes[1];
        } else if (gp.axes.length == 4) {
            // assume axes 0, 2 are for x and 1, 3 are for y
            // use the one with the largest magnitude
            gpX = Math.abs(gp.axes[0]) > Math.abs(gp.axes[2]) ? gp.axes[0] : gp.axes[2];
            gpY = Math.abs(gp.axes[1]) > Math.abs(gp.axes[3]) ? gp.axes[1] : gp.axes[3];
        } else {
            console.error("Unexpected number of axes: ", gp.axes.length);
            return;
        }

        // ignore small values to avoid cursor drift
        if (Math.abs(gpX) < 0.1 && Math.abs(gpY) < 0.1) {
            return;
        }

        updateCursorAndFocus(gpX * sensitivity, gpY * sensitivity, true);
    });
    animationFrameRequest = requestAnimationFrame(gamepadsLoop);
}

