let animationFrameRequest;
let isGamepadConnected = false;

const gamepadHandler = (event, connecting) => {
    const gamepad = event.gamepad;
    if (connecting) {
        console.log("Gamepad connected at index %d: %s. %d buttons, %d axes.",
            gamepad.index, gamepad.id,
            gamepad.buttons.length, gamepad.axes.length);
        if (!isGamepadConnected) {
            isGamepadConnected = true;
            gamepadsLoop();  // start the loop
        }
    } else {
        console.log("Gamepad disconnected from index %d: %s",
            gamepad.index, gamepad.id);
        const gamepads = navigator.getGamepads();
        if (gamepads.length === 0) {
            if (animationFrameRequest) cancelAnimationFrame(animationFrameRequest);  // stop the loop
            isGamepadConnected = false;
        }
    }
}

export const setGamepadHandler = () => {
    window.addEventListener("gamepadconnected", (event) => gamepadHandler(event, true));
    window.addEventListener("gamepaddisconnected", (event) => gamepadHandler(event, false));
}

const gamepadsLoop = () => {
    const gamepads = navigator.getGamepads();
    if (!gamepads) return;

    gamepads.forEach((gp) => {
        // console.log(gp);
    });
    animationFrameRequest = requestAnimationFrame(gamepadsLoop);
}

