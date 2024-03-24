import { getFocusId, getInteractionTimeStats, recordInteraction, resetInteractionTimeHistory, setSockEnv, updateCursorAndFocus } from './cursor.js';
import { setGamepadHandler } from './gamepad.js';
import { onToggleGaze } from './gaze.js';
import { binStr2Rgba, scaleRgba, updateConnectionStatusElement } from './utils.js';
import { handleOffer, handleRemoteIce, setupPeerConnection } from './webrtc.js';

let sockEnv, sockEEG;
let videos, toggleGaze, toggleEEG;

let numClasses, commandLabels, commandColors;  // info from the env server
let command, nextAcceptableCommands;

const charts = [];

let isStarted = false;

const taskCompletionTimer = new easytimer.Timer();

const countdownSec = 3;
const countdownTimer = new easytimer.Timer();

const chartAnimationDuration = 100;  // ms

// error rate
let numSubtaskSelections, numInvalidSubtaskSelections;


document.addEventListener("DOMContentLoaded", () => {
    videos = document.querySelectorAll('video');
    toggleGaze = document.getElementById('toggle-gaze');
    toggleEEG = document.getElementById('toggle-eeg');

    connectEnv();
    toggleGaze.addEventListener('change', () => onToggleGaze(toggleGaze.checked));
    toggleEEG.addEventListener('change', () => onToggleEEG(toggleEEG.checked));

    // Move the cursor to the mouse position
    document.addEventListener('mousemove', (event) => {
        updateCursorAndFocus(event.clientX, event.clientY);
    });

    // Send pressed/released keys to the server
    document.addEventListener('keydown', (event) => {
        if (!isStarted) {
            updateLog("Task not started yet");
            return;
        }
        if (sockEnv.connected) sockEnv.emit('keydown', event.key);
    });
    document.addEventListener('keyup', (event) => {
        if (!isStarted) return;
        if (sockEnv.connected) sockEnv.emit('keyup', event.key);
    });
    setGamepadHandler();

    // buttons
    document.getElementById('start-button').addEventListener('click', startTask);
    document.getElementById('reset-button').addEventListener('click', resetTask);
    document.getElementById('stop-button').addEventListener('click', stopTask);

    // TODO: set initial state of buttons and task status message according to the task status
    updateTaskStatusMsg('Ready.');
    document.getElementById('start-button').disabled = false;
    document.getElementById('reset-button').disabled = false;
    document.getElementById('stop-button').disabled = false;
});

const updateTaskStatusMsg = (msg) => {
    document.getElementById('task-status-message').innerText = msg;
}

const updateLog = (msg, numSpace = 0) => {
    const log = document.getElementById('log');
    log.innerHTML += '&nbsp;'.repeat(numSpace) + msg + "<br>";
    log.scrollTop = log.scrollHeight;
}

const startTask = async () => {
    document.getElementById('start-button').disabled = true;
    document.getElementById('reset-button').disabled = true;

    // countdown
    const _updateCountdownMsg = () => updateTaskStatusMsg(`Start in ${countdownTimer.getTimeValues().seconds} sec...`);
    countdownTimer.start({ countdown: true, startValues: { seconds: countdownSec } });
    _updateCountdownMsg();
    countdownTimer.addEventListener('secondsUpdated', _updateCountdownMsg);
    await new Promise(resolve => countdownTimer.addEventListener('targetAchieved', resolve));
    countdownTimer.stop();
    countdownTimer.removeEventListener('secondsUpdated', _updateCountdownMsg);
    updateTaskStatusMsg('Running...');

    // reset the subtask selection error rate
    numSubtaskSelections = 0;
    numInvalidSubtaskSelections = 0;

    // start the timer
    taskCompletionTimer.start({ precision: 'secondTenths' });

    isStarted = true;
}

const stopTask = () => {
    // if (!isStarted) return;  // TODO
    isStarted = false;

    // task completion time
    let taskCompletionSec = null;
    if (taskCompletionTimer.isRunning()) {
        taskCompletionSec = taskCompletionTimer.getTotalTimeValues().secondTenths / 10;
        taskCompletionTimer.stop();
    }
    if (countdownTimer.isRunning()) countdownTimer.stop();

    // error rate
    const errorRate = numSubtaskSelections === 0 ? 0 : numInvalidSubtaskSelections / numSubtaskSelections;

    sockEnv.emit('taskStop', () => {
        updateTaskStatusMsg("Stopped.")
        // document.getElementById('start-button').disabled = false;
        document.getElementById('reset-button').disabled = false;
    });

    return { taskCompletionSec, errorRate };
}

const resetTask = async () => {
    sockEnv.emit('taskReset', () => {
        updateTaskStatusMsg('Environment reset. Ready.');
        document.getElementById('start-button').disabled = false;
    });
    resetInteractionTimeHistory();
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
        numClasses = labels.length;
        commandLabels = labels;

        command = Array(numAgents).fill('');
        nextAcceptableCommands = Array(numAgents).fill([]);

        updateLog(`Env: ${numClasses} classes, ${numAgents} agents`);
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
                const sec = recordInteraction();
                updateLog(`Agent ${agentId}: Interaction recorded, ${sec.toFixed(1)}s`);
            }

            // reassign the robot selection (to reset the interaction timer)
            updateCursorAndFocus(0, 0, true);
        }

        if (!isNowAcceptable) {
            // agent is executing an action
            // Currently we do not count this as a subtask selection
            updateLog(`Agent ${agentId}: Command update failed`);
            updateLog(`The agent is executing an action`, 15);
        } else if (!hasSubtaskNotDone) {
            // subtask has already been done
            updateLog(`Agent ${agentId}: Command update failed`);
            updateLog(`The subtask "${_command}" has already been done`, 15);

            if (_command !== '') {  // _command==='' should not happen actually
                // This case is considered an "invalid" command
                numInvalidSubtaskSelections++;
                numSubtaskSelections++;
            }
        } else {
            // command is valid and updated
            command[agentId] = _command;
            nextAcceptableCommands[agentId] = _nextAcceptableCommands;

            updateChartColor(charts[agentId], command[agentId], nextAcceptableCommands[agentId]);

            if (_command !== '') {
                numSubtaskSelections++;

                updateLog(`Agent ${agentId}: Command updated to "${_command}"`);
                // console.log(`Next acceptable commands: ${_nextAcceptableCommands.map(c => c === null ? 'null' : c)}`)
            }
        }
    });
    sockEnv.on('subtaskDone', ({ agentId, subtask }) => {
        updateLog(`Agent ${agentId}: Subtask "${subtask}" done`);
    });
    sockEnv.on('taskDone', () => {
        const { taskCompletionSec, errorRate } = stopTask();
        const { len, mean, std } = getInteractionTimeStats();
        updateLog(`<br>Task completed!`);
        updateLog(`Task completion time: ${taskCompletionSec.toFixed(1)} sec`);
        updateLog(`Average time for ${len} interactions: ${mean.toFixed(1)} ± ${std.toFixed(1)} sec`);
        updateLog(`Error rate: ${numInvalidSubtaskSelections}/${numSubtaskSelections} = ${errorRate.toFixed(2)}<br>`);
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
            sockEEG.emit('init', { numClasses: numClasses });
            updateConnectionStatusElement('connected', 'toggle-eeg');
            console.log("EEG server connected");
        });
        sockEEG.on('disconnect', () => {
            updateConnectionStatusElement('disconnected', 'toggle-eeg');
            removeCharts(charts);
            console.log("EEG server disconnected");
        });
        sockEEG.on('reconnect_attempt', () => {  // TODO: not working
            console.log("EEG server reconnecting...");
        });
        sockEEG.on('init', (data) => {
            if (charts.length > 0) removeCharts(charts);
            createCharts(data.threshold);
        });
        sockEEG.on('eeg', ({ cls, likelihoods }) => {
            if (!isStarted) return;

            // forward the command to the env server
            const command = cls === null ? "" : commandLabels[cls];
            sockEnv.emit('eeg', command);
            // console.log(`EEG data received:\n command "${command}"\n likelihoods ${likelihoods.map(l => l.toFixed(2))}`);

            // update the chart data
            const focusId = getFocusId();
            updateChartData(focusId, likelihoods);
        });
    } else {
        if (sockEEG.connected) sockEEG.disconnect();
        removeCharts(charts);
    }
}

const createCharts = (thres) => {
    [...document.getElementsByClassName('likelihood-chart')].forEach((canvas) => {
        // create a config for each chart so that they don't share the same data
        const config = {
            type: 'bar',
            data: {
                labels: Array(numClasses).fill(''),  // neccesary
                datasets: [{
                    data: Array(numClasses).fill(0.4),
                    backgroundColor: commandColors,
                    borderColor: commandColors.map(rgba => scaleRgba(rgba, 0.7, 1)),
                    borderWidth: 1,
                }]
            },
            options: {
                plugins: {
                    legend: {
                        display: false,
                    },
                    annotation: {
                        annotations: {
                            lineThres: {
                                type: 'line',
                                yMin: thres,
                                yMax: thres,
                                borderColor: 'black',
                                borderWidth: 1,
                                borderDash: [4, 4], // dashed line style
                            }
                        }
                    },
                },
                scales: {
                    x: {
                        ticks: {
                            display: false,
                        },
                        grid: {
                            display: false,
                        }
                    },
                    y: {
                        beginAtZero: true,
                        max: thres / 0.7,
                        ticks: {
                            display: false,
                            // display: true,
                            // stepSize: 0.1,
                            // callback: (value) => [0, 0.3, 1].includes(value) ? value : '',
                        },
                        grid: {
                            display: false,
                        }
                    },
                },
                animation: {
                    duration: chartAnimationDuration,
                },
                maintainAspectRatio: false,
                backgroundColor: 'white',
            },
        };
        const chart = new Chart(canvas.getContext('2d'), config);
        chart.update();
        charts.push(chart);
        canvas.parentElement.style.display = 'block';  // show the parent container
    });
}

const removeCharts = () => {
    while (charts.length > 0) {
        const chart = charts.pop();
        chart.canvas.parentElement.style.display = 'none';
        chart.destroy();
    }
};

const updateChartData = (agentId, likelihoods) => {
    const chart = charts[agentId];
    if (chart === undefined) return;

    // update only the likelihood of acceptable commands
    chart.data.datasets[0].data = likelihoods.map((likelihood, i) =>
        nextAcceptableCommands[agentId].includes(commandLabels[i]) ? likelihood : chart.data.datasets[0].data[i]
    );
    chart.update();
}

const updateChartColor = (chart, currentCommand, nextAcceptableCommands) => {
    if (chart === undefined) return;

    const modBg = (barId) => {
        // highlight the current command bar
        if (commandLabels[barId] === currentCommand) return scaleRgba(commandColors[barId], 1, 1);
        // nothing for border color
        return commandColors[barId];
    }
    const modBorder = (barId) => {
        // add black border to the current command bar
        if (commandLabels[barId] === currentCommand) return 'rgba(0, 0, 0, 1)';
        // remove border from the unacceptable command bars
        if (nextAcceptableCommands.includes(commandLabels[barId])) return scaleRgba(commandColors[barId], 0.7, 1);
        return 'rgba(255, 255, 255, 1)';
    }
    chart.data.datasets[0].backgroundColor = [...Array(numClasses).keys()].map(modBg);
    chart.data.datasets[0].borderColor = [...Array(numClasses).keys()].map(modBorder);
    chart.update();
}
