import { createCharts, resetChartData, updateChartColor, updateChartData } from './chart.js';
import { getFocusId, getInteractionTimeStats, recordInteractionTime, resetInteractionTime, resetInteractionTimeHistory, setSockEnv, updateCursorAndFocus } from './cursor.js';
import { setGamepadHandler } from './gamepad.js';
import { onToggleGaze } from './gaze.js';
import { binStr2Rgba, updateConnectionStatusElement } from './utils.js';
import { handleOffer, handleRemoteIce, setupPeerConnection } from './webrtc.js';

let sockEnv, sockEEG;
let videos, toggleGaze, toggleEEG;

let commandLabels, commandColors;  // info from the env server
let command, nextAcceptableCommands;
let keyMap;

let isStarted = false;

const taskCompletionTimer = new easytimer.Timer();

const countdownSec = 3;
const countdownTimer = new easytimer.Timer();

// error rate
let numSubtaskSelections, numInvalidSubtaskSelections;


document.addEventListener("DOMContentLoaded", () => {
    videos = document.querySelectorAll('video');
    toggleGaze = document.getElementById('toggle-gaze');
    toggleEEG = document.getElementById('toggle-eeg');

    connectEnv();
    toggleGaze.addEventListener('change', () => onToggleGaze(toggleGaze.checked));
    toggleEEG.addEventListener('change', () => onToggleEEG(toggleEEG.checked));

    // Move the cursor by mouse
    document.addEventListener('mousemove', (event) => {
        updateCursorAndFocus(event.clientX, event.clientY);
    });
    // Move the cursor by gamepad
    setGamepadHandler();

    // subtask selection by keyboard
    document.addEventListener('keydown', (event) => {
        if (keyMap === undefined || !keyMap.hasOwnProperty(event.key)) return;
        onSubtaskSelectionEvent(keyMap[event.key]);
    });

    // buttons
    document.getElementById('start-button').addEventListener('click', startTask);
    document.getElementById('reset-button').addEventListener('click', () => {
        // stop
        const { taskCompletionSec, errorRate } = stopTask();
        updateLog('Task stopped.');
        if (taskCompletionSec !== null) updateLog(`Time: ${taskCompletionSec.toFixed(1)} sec`);
        if (errorRate !== null) updateLog(`Error rate: ${errorRate.toFixed(2)}`);
        // reset
        resetTask();
    });

    resetTask();
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

    // countdown
    if (!await countdown(countdownSec)) return;
    updateTaskStatusMsg('Running...');

    // reset the subtask selection error rate
    numSubtaskSelections = 0;
    numInvalidSubtaskSelections = 0;

    // start the timer
    taskCompletionTimer.start({ precision: 'secondTenths' });

    isStarted = true;
}

const stopTask = () => {
    isStarted = false;

    // task completion time
    let taskCompletionSec = null;
    let errorRate = null;
    if (taskCompletionTimer.isRunning()) {
        taskCompletionSec = taskCompletionTimer.getTotalTimeValues().secondTenths / 10;
        taskCompletionTimer.stop();
    }
    if (countdownTimer.isRunning()) countdownTimer.stop();

    // error rate
    errorRate = numSubtaskSelections === 0 ? null : numInvalidSubtaskSelections / numSubtaskSelections;

    sockEnv.emit('taskStop', () => updateTaskStatusMsg("Stopped."));

    return { taskCompletionSec, errorRate };
}

const resetTask = () => {
    sockEnv.emit('taskReset', () => {
        updateTaskStatusMsg('Environment reset. Ready.');
        document.getElementById('start-button').disabled = false;
        document.getElementById('reset-button').disabled = true;
    });
    resetInteractionTimeHistory();
    resetChartData();
}

const connectEnv = () => {
    // sockEnv: socket for communication with the environment server
    // - WebRTC signaling
    // - focus update notification
    sockEnv = io.connect(`${location.protocol}//${location.hostname}:8000`, { transports: ['websocket'] });
    let pc;

    sockEnv.on('connect', () => {
        updateLog("Env server connected");
        // request WebRTC offer to the server
        sockEnv.emit('webrtc-offer-request');
    });
    sockEnv.on('init', ({ commandLabels: labels, commandColors: colors, numAgents }) => {
        // commandColors: ["001", "010", ...]
        commandColors = colors.map(c => binStr2Rgba(c, 0.3));
        commandLabels = labels;
        updateLog(`Env: ${labels.length} classes, ${numAgents} agents`);

        command = Array(numAgents).fill('');
        nextAcceptableCommands = Array(numAgents).fill([]);

        keyMap = {};
        // cancel: 0, others: 1, 2, ...
        if (commandLabels.includes('cancel')) keyMap['0'] = 'cancel';
        commandLabels.filter(label => label !== 'cancel').forEach((label, idx) => {
            keyMap[(idx + 1).toString()] = label;
        });

        // if video is ready, create charts
        videos[0].addEventListener('canplay', () => createCharts(commandColors, commandLabels));
    });
    sockEnv.on('command', (data) => {
        // this event should be emitted only after the 'init' event

        // TODO: rename global vars and replace "data"
        const agentId = data.agentId;
        const _command = data.command;
        const _nextAcceptableCommands = data.nextAcceptableCommands;
        const isNowAcceptable = data.isNowAcceptable;
        const hasSubtaskNotDone = data.hasSubtaskNotDone;

        if (_command !== '') {
            // record the interaction if the command is now acceptable
            // regardless of whether the command is "valid" subtask selection (data.hasSubtaskNotDone)
            if (isNowAcceptable) {
                const sec = recordInteractionTime();
                updateLog(`Agent ${agentId}: Interaction recorded, ${sec.toFixed(1)}s`);
            }

            // reset interaction time regardless of hasSubtaskNotDone and isNowAcceptable
            resetInteractionTime();
        }

        if (!isNowAcceptable) {
            // agent is executing an action
            // Currently we do not count this as a subtask selection
            updateLog(`Agent ${agentId}: Command update failed`);
            updateLog(`Agent is executing an action`, 2);
        } else if (!hasSubtaskNotDone) {
            // subtask has already been done
            updateLog(`Agent ${agentId}: Command update failed`);
            updateLog(`Task "${_command}" is already done`, 2);

            if (_command !== '') {  // _command==='' should not happen actually
                // This case is considered an "invalid" command
                numInvalidSubtaskSelections++;
                numSubtaskSelections++;
            }
        } else {
            // command is valid and updated
            command[agentId] = _command;
            nextAcceptableCommands[agentId] = _nextAcceptableCommands;

            updateChartColor(agentId, command[agentId], nextAcceptableCommands[agentId]);

            if (_command !== '') {
                numSubtaskSelections++;

                updateLog(`Agent ${agentId}: Command updated to "${_command}"`);
                // console.log(`Next acceptable commands: ${_nextAcceptableCommands.map(c => c === null ? 'null' : c)}`)
            }
        }
    });
    sockEnv.on('subtaskDone', ({ agentId, subtask }) => {
        updateLog(`Agent ${agentId}: Subtask "${subtask}" done`);
        if (getFocusId() === agentId) resetInteractionTime();  // reset the timer if the agent is selected so that the time during the subtask is not counted
    });
    sockEnv.on('taskDone', () => {
        const { taskCompletionSec, errorRate } = stopTask();
        const { len, mean, std } = getInteractionTimeStats();
        updateLog(`\nTask completed!`);
        updateLog(`Task completion time:`);
        updateLog(`${taskCompletionSec.toFixed(1)} sec`, 2);
        updateLog(`Average time for ${len} interactions:`);
        updateLog(`${mean.toFixed(1)} ± ${std.toFixed(1)} sec`, 2);
        updateLog(`Error rate:`);
        updateLog(`${numInvalidSubtaskSelections}/${numSubtaskSelections} = ${errorRate.toFixed(2)}\n`, 2);
    });
    sockEnv.on('webrtc-offer', async (data) => {
        console.log("WebRTC offer received");
        pc = setupPeerConnection(sockEnv, videos);
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

const onToggleEEG = (checked) => {
    if (checked) {
        updateConnectionStatusElement('connecting', 'toggle-eeg');
        sockEEG = io.connect(`http://localhost:8002`, { transports: ['websocket'] });  // TODO: https?
        sockEEG.on('connect', () => {
            sockEEG.emit('init', { numClasses: commandLabels.length });
            updateConnectionStatusElement('connected', 'toggle-eeg');
            console.log("EEG server connected");
        });
        sockEEG.on('disconnect', () => {
            updateConnectionStatusElement('disconnected', 'toggle-eeg');
            console.log("EEG server disconnected");
        });
        sockEEG.on('reconnect_attempt', () => {  // TODO: not working
            console.log("EEG server reconnecting...");
        });
        sockEEG.on('eeg', ({ cls, likelihoods }) => onSubtaskSelectionEvent(cls, likelihoods));
    } else {
        if (sockEEG.connected) sockEEG.disconnect();
    }
}

const onSubtaskSelectionEvent = (command, likelihoods = undefined) => {
    if (!isStarted) return;
    if (!sockEnv.connected) return;

    const agentId = getFocusId();
    if (agentId === null) return;

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

    if (commandLabel !== '') {
        sockEnv.emit('command', { agentId: agentId, command: commandLabel });
    }

    if (likelihoods === undefined) {
        likelihoods = commandLabels.map(label => label === commandLabel ? 1 : 0);
    }
    // update the chart data
    updateChartData(agentId, likelihoods, nextAcceptableCommands[agentId]);
}
