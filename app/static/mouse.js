import { updateCursorAndFocus } from './cursor.js';

export const onToggleMouse = (checked) => {
    if (checked) {
        document.addEventListener('mousemove', onMousemove);
        document.body.style.cursor = 'none';  // hide mouse cursor
    } else {
        document.removeEventListener('mousemove', onMousemove);
        document.body.style.cursor = 'auto';  // show mouse cursor
    }
}

const onMousemove = (event) => {
    updateCursorAndFocus(event.clientX, event.clientY);
}

