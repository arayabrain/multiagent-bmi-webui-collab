import { createCharts, resetChartData, updateChartColor, updateChartData, updateChartLock } from './chart.js';
import { getFocusId, getInteractionTimeStats, recordInteractionTime, resetInteractionTimeHistory, resetInteractionTimer, setSockEnv } from './cursor.js';
import { startDataCollection, stopDataCollection } from './dataCollection.js';
import { onToggleEEG, sendDataCollectionOnset } from './eeg.js';
import { setGamepadHandler } from './gamepad.js';
import { onToggleGaze } from './gaze.js';
import { onToggleKeyboard } from './keyboard.js';
import { onToggleMouse } from './mouse.js';
import { binStr2Rgba } from './utils.js';
import { handleOffer, handleRemoteIce, setupPeerConnection } from './webrtc.js';

const countdownSec = 3;

let sockEnv;
let commandLabels, commandColors;  // info from the env server
let isStarted = false;  // if true, task is started and accepting subtask selection
let isDataCollection = false;
let userinfo;
let numSubtaskSelections, numInvalidSubtaskSelections;  // error rate
const countdownTimer = new easytimer.Timer();
const taskCompletionTimer = new easytimer.Timer();
const expId = dateFns.format(new Date(), 'yyyyMMdd_HHmmss');

document.addEventListener("DOMContentLoaded", async () => {
    connectEnv();

    // username input
    // TODO: use sessionStorage
    const res = await fetch('/api/getuser');
    userinfo = await res.json();
    document.getElementById('username').textContent = `User: ${userinfo.username}`;

    // buttons
    document.getElementById('start-button').addEventListener('click', startTask);
    document.getElementById('reset-button').addEventListener('click', () => {
        stopTask();
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
    document.querySelectorAll('.toggle-container .togglable').forEach(input => input.disabled = true);

    // countdown
    if (!await countdown(countdownSec)) return;
    updateTaskStatusMsg('Running...');
    updateLog('\nStarted.');

    if (isDataCollection) {
        document.addEventListener('dataCollectionOnset', async (event) => {
            sendDataCollectionOnset(event);  // eeg server; TODO: also for other devices?
            updateLog(`Cue: ${event.detail.cue}`);
        });
        document.addEventListener('dataCollectionCompleted', async () => {
            stopTask(true);
        });
        startDataCollection(commandColors, commandLabels);
    } else {
        // start the metrics measurement
        taskCompletionTimer.start({ precision: 'secondTenths' });
    }

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

    // stop the metrics measurement and get the results
    const taskCompletionSec = taskCompletionTimer.getTotalTimeValues().secondTenths / 10;
    const errorRate = numSubtaskSelections === 0 ? null : numInvalidSubtaskSelections / numSubtaskSelections;
    const { len, mean, std } = getInteractionTimeStats();
    taskCompletionTimer.stop();

    // stop the agents
    const status = isComplete ? 'Completed!' : 'Stopped.';
    updateLog(`\n${status}`);
    sockEnv.emit('taskStop', () => {
        updateTaskStatusMsg(status);
        updateLog('Agent stopped.');
    });

    if (isDataCollection) {
        stopDataCollection();
    } else {
        // show logs
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

        // send the metrics to the server if the task is completed
        if (isComplete) {
            sockEnv.emit('saveMetrics', {
                userInfo: userinfo,
                expId: expId,
                taskCompletionTime: taskCompletionSec,
                errorRate: { numInvalidSubtaskSelections, numSubtaskSelections, rate: errorRate },
                interactionTime: { len, mean, std },
                devices: JSON.parse(sessionStorage.getItem('deviceSelection')),
            }, (res) => {
                if (res) {
                    updateLog('Metrics saved.');
                } else {
                    updateLog('Failed to save metrics.');
                }
            });
        }
    }

    // Popup for repeat or back to menu
    // This ensures the expId is not reused
    if (isComplete) {
        const modal = document.getElementById('task-complete-modal');
        const modalInstance = new bootstrap.Modal(modal);
        modalInstance.show();
    }
}

const resetTask = () => {
    console.assert(!isStarted, 'Task is not stopped');
    sockEnv.emit('taskReset', () => {
        updateTaskStatusMsg('Environment reset. Ready.');
        document.getElementById('start-button').disabled = false;
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
    sockEnv.on('init', ({ isDataCollection: idc, commandLabels: labels, commandColors: colors }) => {
        isDataCollection = idc;
        // commandColors: ["001", "010", ...]
        commandColors = colors.map(c => binStr2Rgba(c, 0.3));
        commandLabels = labels;
        updateLog(`Environment initialized`);

        // if a video is ready, create charts
        document.querySelector('video').addEventListener('canplay', () => createCharts(commandColors, commandLabels));

        // initialize the selected devices
        const deviceSelection = JSON.parse(sessionStorage.getItem('deviceSelection'));
        // robot selection devices
        if (deviceSelection.mouse) onToggleMouse(true);
        if (deviceSelection.gaze) onToggleGaze(true);
        // subtask selection devices
        if (deviceSelection.keyboard) onToggleKeyboard(true, onSubtaskSelectionEvent, commandLabels, userinfo.username, expId);
        if (deviceSelection.eeg) onToggleEEG(true, onSubtaskSelectionEvent, commandLabels, userinfo.username, expId);
        // both
        if (deviceSelection.gamepad) setGamepadHandler(true, onSubtaskSelectionEvent, commandLabels, userinfo.username, expId);
    });
    sockEnv.on('command', ({ agentId, command, nextAcceptableCommands, isNowAcceptable, hasSubtaskNotDone, likelihoods }) => {
        // interaction time
        if (command !== '') {
            // record the interaction if the command is now acceptable
            // regardless of whether the command is "valid" (hasSubtaskNotDone) subtask selection
            if (isNowAcceptable) {
                const sec = recordInteractionTime();
                updateLog(`Agent ${agentId}: Interaction recorded, ${sec.toFixed(1)}s`);
            }
            // reset interaction timer regardless of hasSubtaskNotDone and isNowAcceptable
            resetInteractionTimer();
        }

        // error rate and chart update
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
            numInvalidSubtaskSelections++;
            numSubtaskSelections++;
        } else {
            // Command was valid and updated
            if (command !== '') {
                numSubtaskSelections++;
                updateLog(`Agent ${agentId}: Command updated to "${command}"`);
                if (likelihoods !== null) updateChartData(agentId, likelihoods);  // sync the chart data before updating the lock status
            }
            updateChartLock(agentId, nextAcceptableCommands);
            updateChartColor(agentId, command);
        }
    });
    sockEnv.on('subtaskDone', ({ agentId, subtask }) => {
        updateLog(`Agent ${agentId}: Subtask "${subtask}" done`);
        if (getFocusId() === agentId) resetInteractionTimer();  // reset the timer if the agent is selected so that the time during the subtask is not counted
    });
    sockEnv.on('taskDone', () => stopTask(true));
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
        sockEnv.emit('command', {
            agentId: agentId,
            command: commandLabel,
            likelihoods: likelihoods,
        });
    }
    // update the chart
    updateChartData(agentId, likelihoods);
}
