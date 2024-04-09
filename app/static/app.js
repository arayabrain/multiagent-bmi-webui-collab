import { createCharts, resetChartData, updateChartColor, updateChartData } from './chart.js';
import { getFocusId, getInteractionTimeStats, recordInteractionTime, resetInteractionTime, resetInteractionTimeHistory, setSockEnv } from './cursor.js';
import { onToggleEEG } from './eeg.js';
import { setGamepadHandler } from './gamepad.js';
import { onToggleGaze } from './gaze.js';
import { onToggleKeyboard, setKeyMap } from './keyboard.js';
import { onToggleMouse } from './mouse.js';
import { binStr2Rgba } from './utils.js';
import { handleOffer, handleRemoteIce, setupPeerConnection } from './webrtc.js';

let sockEnv;
let videos;

let commandLabels, commandColors;  // info from the env server
let command, nextAcceptableCommands;

let isStarted = false;  // task is started and accepting subtask selection

const taskCompletionTimer = new easytimer.Timer();

const countdownSec = 3;
const countdownTimer = new easytimer.Timer();

// error rate
let numSubtaskSelections, numInvalidSubtaskSelections;


document.addEventListener("DOMContentLoaded", () => {
    videos = document.querySelectorAll('video');

    connectEnv();

    // robot selection devices
    document.getElementById('toggle-gaze').addEventListener('change', (e) => onToggleGaze(e.target.checked));
    document.getElementById('toggle-mouse').addEventListener('change', (e) => onToggleMouse(e.target.checked));
    setGamepadHandler();
    // subtask selection devices
    document.getElementById('toggle-eeg').addEventListener('change', (e) => onToggleEEG(e.target.checked, onSubtaskSelectionEvent, commandLabels));
    document.getElementById('toggle-keyboard').addEventListener('change', (e) => onToggleKeyboard(e.target.checked, onSubtaskSelectionEvent));
    // dispatch events for initial state
    document.querySelectorAll('.toggle-container .togglable').forEach(input => input.dispatchEvent(new Event('change')));

    // buttons
    document.getElementById('start-button').addEventListener('click', startTask);
    document.getElementById('reset-button').addEventListener('click', () => {
        stopTask();
        resetTask();
    });

    document.getElementById('username').addEventListener('input', () => {
        document.getElementById('start-button').disabled = !isNameValid();
    });

    resetTask();
});

const isNameValid = () => {
    return document.getElementById('username').value.trim() !== '';
}

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
    document.getElementById('username').disabled = true;
    document.getElementById('start-button').disabled = true;
    document.getElementById('reset-button').disabled = false;
    document.querySelectorAll('.toggle-container .togglable').forEach(input => input.disabled = true);

    // countdown
    if (!await countdown(countdownSec)) return;
    updateTaskStatusMsg('Running...');

    // start the timer
    taskCompletionTimer.start({ precision: 'secondTenths' });

    isStarted = true;
}

const stopTask = (isComplete = false) => {
    if (!isStarted) {
        // called by
        // - the stop&reset button during the countdown
        // - the stop&reset button after taskDone
        if (countdownTimer.isRunning()) countdownTimer.stop();
        return;
    }
    isStarted = false;

    // get metrics
    const taskCompletionSec = taskCompletionTimer.getTotalTimeValues().secondTenths / 10;
    taskCompletionTimer.stop();
    const errorRate = numSubtaskSelections === 0 ? null : numInvalidSubtaskSelections / numSubtaskSelections;
    const { len, mean, std } = getInteractionTimeStats();

    // stop the agents
    const status = isComplete ? 'Task Completed!' : 'Stopped.';
    sockEnv.emit('taskStop', () => {
        updateTaskStatusMsg(status);
    });

    // show logs
    updateLog(`\n${status}`);
    if (taskCompletionSec > 0) {
        updateLog(`Time:`);
        updateLog(`${taskCompletionSec.toFixed(1)} sec`, 2);
    }
    if (len !== 0) {
        updateLog(`Average time for ${len} interactions:`);
        updateLog(`${mean.toFixed(2)} ± ${std.toFixed(2)} sec`, 2);
    }
    if (errorRate !== null) {
        updateLog(`Error rate:`);
        updateLog(`${numInvalidSubtaskSelections}/${numSubtaskSelections} = ${errorRate.toFixed(2)}`, 2);
    }
    updateLog('');

    // send the metrics to the server if the task is completed
    if (isComplete) {
        sockEnv.emit('saveMetrics', {
            username: document.getElementById('username').value,
            taskCompletionTime: taskCompletionSec,
            errorRate,
            interactionTime: { len, mean, std },
            devices: {
                mouse: document.getElementById('toggle-mouse').checked,
                gamepad: document.getElementById('toggle-gamepad').checked,
                gaze: document.getElementById('toggle-gaze').checked,
                keyboard: document.getElementById('toggle-keyboard').checked,
                eeg: document.getElementById('toggle-eeg').checked,
            }
        }, (res) => {
            if (res) {
                updateLog('Metrics saved.');
            } else {
                updateLog('Failed to save metrics.');
            }
        });
    }
}

const resetTask = () => {
    console.assert(!isStarted, 'Task is not stopped');
    sockEnv.emit('taskReset', () => {
        updateTaskStatusMsg('Environment reset. Ready.');
        document.getElementById('username').disabled = false;
        document.getElementById('start-button').disabled = !isNameValid();
        document.getElementById('reset-button').disabled = true;
        document.querySelectorAll('.toggle-container .togglable').forEach(input => input.disabled = false);
    });
    resetChartData();
    // reset metrics
    resetInteractionTimeHistory();
    numSubtaskSelections = 0;
    numInvalidSubtaskSelections = 0;
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
        setKeyMap(commandLabels);

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
    sockEnv.on('taskDone', () => stopTask(true));
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
