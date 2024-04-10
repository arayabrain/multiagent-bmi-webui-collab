import { scaleRgba, sleep } from './utils.js';

const numTrialForEachColor = 3;
const goCueDuration = 1000;
const loopInterval = 1000;
let cueColors, commandLabels;
let isRunning = false;

export const startDataCollection = (commandColors, _commandLabels) => {
    if (isRunning) console.error('Data collection is already running.');
    isRunning = true;

    cueColors = commandColors.map(c => scaleRgba(c, 1, 0.5));
    commandLabels = _commandLabels;
    const colorIdxList = generateColorIdxList(numTrialForEachColor);
    const cue = createCue();
    loopDataCollection(colorIdxList, cue, 2);
}

export const stopDataCollection = (cue) => {
    isRunning = false;
    if (!cue) cue = document.getElementById('cue');
    if (cue) cue.parentElement.removeChild(cue);
}

const createCue = () => {
    const cue = document.createElement('div');
    cue.id = 'cue';
    cue.style.position = 'absolute';
    cue.style.top = '50%';
    cue.style.left = '50%';
    cue.style.transform = 'translate(-50%, -50%)';
    cue.style.width = '15%';
    cue.style.height = '0';
    cue.style.paddingTop = '15%';
    cue.style.color = 'white';
    // cue.style.backgroundColor = 'rgba(255, 0, 0, 0.5)';
    // cue.style.fontSize = '2em';
    cue.style.fontSize = '2.5vw';
    cue.style.padding = '1em';
    cue.style.display = 'none';
    cue.style.textAlign = 'center';
    cue.style.justifyContent = 'center';
    cue.style.alignItems = 'center';

    document.querySelector('video').parentElement.appendChild(cue);
    return cue;
}

const loopDataCollection = async (colorIdxList, cue, sec) => {
    let _sec = sec;

    while (colorIdxList.length > 0 && isRunning) {
        const colorIdx = colorIdxList.pop();  // LIFO
        cue.innerText = _sec.toString();
        cue.style.backgroundColor = cueColors[colorIdx];
        cue.style.display = 'flex';

        // countdown
        while (_sec > 0) {
            await sleep(1000);
            if (!isRunning) return;
            cue.innerText = --_sec;
        }
        // show 'Go' for 1 sec and hide it
        cue.innerText = 'Go';
        document.dispatchEvent(new CustomEvent(
            'dataCollectionOnset',
            { detail: { cue: commandLabels[colorIdx], timestamp: Date.now() } }));
        await sleep(goCueDuration);  // user should make a command during this time
        if (!isRunning) return;
        cue.style.display = 'none';

        // start next loop in 1 sec
        await sleep(loopInterval);
        _sec = sec;
    }
    if (colorIdxList.length === 0 && isRunning) {
        stopDataCollection(cue);
        document.dispatchEvent(new CustomEvent('dataCollectionCompleted'));
    }
}

const generateColorIdxList = (numTrialForEachColor) => {
    // generate random-order color index list
    const colorIdxs = [];
    [...Array(cueColors.length).keys()].forEach(idx => {
        for (let i = 0; i < numTrialForEachColor; i++) {
            colorIdxs.push(idx);
        }
    });

    // Shuffle the array
    for (let i = colorIdxs.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [colorIdxs[i], colorIdxs[j]] = [colorIdxs[j], colorIdxs[i]];
    }
    return colorIdxs;
}
