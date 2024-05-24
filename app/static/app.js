import { createCharts, resetChartData, updateChartColor, updateChartData, updateChartLock } from './chart.js';
import { getFocusId, getInteractionTime, resetInteractionTimer, setSockEnv } from './cursor.js';
import { startDataCollection, stopDataCollection } from './dataCollection.js';
import { init as initEEG, sendDataCollectionOnset } from './eeg.js';
import { init as initGamepad } from './gamepad.js';
import { init as initGaze } from './gaze.js';
import { init as initKeyboard } from './keyboard.js';
import { init as initMouse } from './mouse.js';
import { binStr2Rgba } from './utils.js';
import { handleOffer, handleRemoteIce, setupPeerConnection } from './webrtc.js';

const robotSelectionDeviceInitFuncs = {
    mouse: initMouse,
    gaze: initGaze,
};
const subtaskSelectionDeviceInitFuncs = {
    keyboard: initKeyboard,
    gamepad: initGamepad,
    eeg: initEEG,
};

const countdownSec = 3;
let sockEnv, userinfo, commandLabels, commandColors;
let isStarted = false;  // if true, task is started and accepting subtask selection
let isDataCollection = false;
const countdownTimer = new easytimer.Timer();

document.addEventListener("DOMContentLoaded", async () => {
    connectEnv();

    // get userinfo
    const response = await fetch('/api/getuser');
    userinfo = await response.json();
    document.getElementById('username-area').textContent = `User: ${userinfo.name}`;

    // buttons
    document.getElementById('start-button').addEventListener('click', startTask);
    document.getElementById('reset-button').addEventListener('click', () => {
        stopTask();
        if (isDataCollection) {
            location.reload();  // Force data collection recorder to restart
        } else {
            resetClient();
        }
    });

    resetClient();
});

const updateTaskStatusMsg = (msg) => {
    document.getElementById('task-status-message').innerText = msg;
}

const updateLog = (msg, numSpace = 0) => {
    const log = document.getElementById('log');
    log.textContent += ' '.repeat(numSpace) + msg + '\n';
    log.scrollTop = log.scrollHeight;
}

const countdown = async (sec) => {
    const _updateCountdownMsg = () => updateTaskStatusMsg(`Start in ${countdownTimer.getTimeValues().seconds} sec...`);

    countdownTimer.start({ countdown: true, startValues: { seconds: sec } });
    _updateCountdownMsg();
    countdownTimer.addEventListener('secondsUpdated', _updateCountdownMsg);

    const timeoutPromise = new Promise((resolve) => setTimeout(() => resolve('timeout'), (sec + 1) * 1000));
    const countdownPromise = new Promise((resolve) => countdownTimer.addEventListener('targetAchieved', () => resolve('targetAchieved')));
    const result = await Promise.race([timeoutPromise, countdownPromise]);

    countdownTimer.stop();
    countdownTimer.removeEventListener('secondsUpdated', _updateCountdownMsg);
    return result === 'targetAchieved';
}

const startTask = async () => {
    document.getElementById('start-button').disabled = true;
    document.getElementById('reset-button').disabled = false;
    document.querySelectorAll('.toggle-container .togglable').forEach(input => input.disabled = true);

    if (!await countdown(countdownSec)) return;  // countdown

    sockEnv.emit(
        'taskStart',
        {
            userinfo: userinfo,
            deviceSelection: JSON.parse(sessionStorage.getItem('deviceSelection')),
        },
        () => {
            updateTaskStatusMsg('Running...');
            updateLog('\nStarted.');
        }
    );

    if (isDataCollection) {
        document.addEventListener('dataCollectionOnset', onDataCollectionOnset);
        document.addEventListener('dataCollectionCompleted', onDataCollectionCompleted);
        startDataCollection(commandColors, commandLabels);
    }

    isStarted = true;
}


const onDataCollectionOnset = async (event) => {
    sendDataCollectionOnset(event);  // eeg server; TODO: also for other devices?
    updateLog(`Cue: ${event.detail.cue}`);
};

const onDataCollectionCompleted = async () => {
    stopTask(true);
};


const stopTask = (isComplete = false) => {
    if (!isStarted) {
        // called by
        // - the stop&reset button during the countdown
        // - the stop&reset button after taskDone
        // - the taskStopDone event from the server after pressing the stop&reset button
        if (countdownTimer.isRunning()) countdownTimer.stop();
        return;
    }
    isStarted = false;

    // stop the agents
    const status = isComplete ? 'Completed!' : 'Stopped.';
    updateLog(`\n${status}`);
    sockEnv.emit('taskStop', () => {
        updateTaskStatusMsg(status);
        updateLog('Agent stopped.');
    });

    if (isDataCollection) {
        stopDataCollection();
        document.removeEventListener('dataCollectionOnset', onDataCollectionOnset);
        document.removeEventListener('dataCollectionCompleted', onDataCollectionCompleted);
    }

    // Popup for repeat or back to menu
    // This ensures the expId is not reused
    if (isComplete) {
        const modal = document.getElementById('task-complete-modal');
        const modalInstance = new bootstrap.Modal(modal);
        modalInstance.show();
    }
}

const resetClient = () => {
    document.getElementById('start-button').disabled = false;
    document.getElementById('reset-button').disabled = true;
    resetChartData();
}

const connectEnv = () => {
    // sockEnv: socket for communication with the environment server
    // - WebRTC signaling
    // - focus update notification
    console.log(location.pathname)
    sockEnv = io.connect(`${location.protocol}//${location.hostname}:8000`, {
        transports: ['websocket'],
        query: { endpoint: location.pathname },
    });
    let pc;

    sockEnv.on('connect', () => {
        updateLog("Env server connected");
        // request WebRTC offer to the server
        sockEnv.emit('webrtc-offer-request');
    });
    sockEnv.on('status', (status) => {
        const msg = status.isRunning ? 'Running...' : 'Ready.';
        updateTaskStatusMsg(msg);
    });
    sockEnv.on('init', ({ expId, isDataCollection: idc, commandLabels: labels, commandColors: colors }) => {
        isDataCollection = idc;
        // commandColors: ["001", "010", ...]
        commandColors = colors.map(c => binStr2Rgba(c, 0.3));
        commandLabels = labels;
        updateLog(`Environment initialized`);

        // if a video is ready, create charts
        document.querySelector('video').addEventListener('canplay', () => createCharts(commandColors, commandLabels));

        // initialize the selected devices
        const deviceSelection = JSON.parse(sessionStorage.getItem('deviceSelection'));
        Object.keys(robotSelectionDeviceInitFuncs).forEach(device => {
            if (deviceSelection[device]) robotSelectionDeviceInitFuncs[device]();
        });
        Object.keys(subtaskSelectionDeviceInitFuncs).forEach(device => {
            if (deviceSelection[device]) subtaskSelectionDeviceInitFuncs[device](onSubtaskSelectionEvent, commandLabels, userinfo.name, expId);
        });
    });
    sockEnv.on('command', ({ agentId, command, nextAcceptableCommands, isNowAcceptable, hasSubtaskNotDone, likelihoods, interactionTime }) => {
        if (interactionTime) {
            updateLog(`Agent ${agentId}: Interaction time ${interactionTime.toFixed(1)}s`);
        }
        if (!isNowAcceptable) {
            // Command was not updated because agent was already executing an action
            // Currently we do not count this as a subtask selection
            updateLog(`Agent ${agentId}: Command update failed`);
            updateLog(`Agent is executing an action`, 2);
        } else if (!hasSubtaskNotDone) {
            // Command was not updated because the selected subtask has already been done
            // We consider this as an "invalid" subtask selection and count as an error
            updateLog(`Agent ${agentId}: Command update failed`);
            updateLog(`Task "${command}" is already done`, 2);
            console.assert(command !== '', 'empty command');
        } else {
            // Command was valid and updated
            if (command !== '') {
                updateLog(`Agent ${agentId}: Command updated to "${command}"`);
                if (likelihoods !== null) updateChartData(agentId, likelihoods);  // sync the chart data before updating the lock status
            }
            updateChartLock(agentId, nextAcceptableCommands);
            updateChartColor(agentId, command);
        }
    });
    sockEnv.on('taskStopDone', () => {
        document.getElementById('reset-button').click();  // If another user triggers a stop&reset, me also do it
    });
    sockEnv.on('subtaskDone', ({ agentId, subtask }) => {  // TODO: subtaskCompleted
        updateLog(`Agent ${agentId}: Subtask "${subtask}" done`);
        if (getFocusId() === agentId) resetInteractionTimer();  // reset the timer if the agent is selected so that the time during the subtask is not counted
    });
    sockEnv.on('taskDone', () => {  // TODO: taskCompleted
        stopTask(true);
    });
    sockEnv.on('webrtc-offer', async (data) => {
        console.log("WebRTC offer received");
        pc = setupPeerConnection(sockEnv, document.querySelectorAll('video'));
        await handleOffer(sockEnv, pc, data);
    });
    sockEnv.on('webrtc-ice', async (data) => {
        await handleRemoteIce(pc, data);
    });
    sockEnv.on('disconnect', async () => {
        console.log('Env Server disconnected');
    });

    setSockEnv(sockEnv);
}

const onSubtaskSelectionEvent = (command, likelihoods = undefined) => {
    if (!isStarted) return;
    if (!sockEnv.connected) return;
    if (isDataCollection) return;  // For now, do not send commands during data collection

    const agentId = getFocusId();
    if (agentId === null) return;

    // get the command label
    let commandLabel;
    if (command === null) {
        commandLabel = '';
    } else if (typeof command === 'number') {
        commandLabel = commandLabels[command];
    } else if (typeof command === 'string' && commandLabels.includes(command)) {
        commandLabel = command;
    } else {
        console.error(`Invalid command: ${command}`);
        return;
    }

    // set likelihoods if not provided
    if (likelihoods === undefined) {
        likelihoods = commandLabels.map(label => label === commandLabel ? 1 : 0);
    }
    // send the command and likelihoods to the server
    if (commandLabel !== '') {
        // get the interaction time
        const interactionTime = getInteractionTime();
        resetInteractionTimer();

        sockEnv.emit('command', {
            agentId: agentId,
            command: commandLabel,
            likelihoods: likelihoods,
            interactionTime: interactionTime,
        });
    }
    // update the chart
    updateChartData(agentId, likelihoods);
}
