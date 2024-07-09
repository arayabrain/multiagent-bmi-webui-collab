import { updateCursorAndFocus } from './cursor.js';
import { updateDeviceStatus } from './utils.js';


export const init = () => {
    document.addEventListener('mousemove', onMousemove);
    document.body.style.cursor = 'none';  // hide mouse cursor
    updateDeviceStatus('Mouse', 'connected');
}

const onMousemove = (event) => {
    updateCursorAndFocus(event.clientX, event.clientY);
}

