import { getFocusId, setSockEnv, updateCursorAndFocus } from './cursor.js';
import { setGamepadHandler } from './gamepad.js';
import { onToggleGaze } from './gaze.js';
import { binStr2Rgba, scaleRgba, updateConnectionStatusElement } from './utils.js';
import { handleOffer, handleRemoteIce, setupPeerConnection } from './webrtc.js';

let sockEnv, sockEEG;
let videos, toggleGaze, toggleEEG;
let numClasses, command, nextAcceptableCommands;  // info from the env server
let barColors, barBorderColors;
const charts = [];

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
        if (sockEnv.connected) sockEnv.emit('keydown', event.key);
    });
    document.addEventListener('keyup', (event) => {
        if (sockEnv.connected) sockEnv.emit('keyup', event.key);
    });
    setGamepadHandler();
});

const connectEnv = () => {
    // sockEnv: socket for communication with the environment server
    // - WebRTC signaling
    // - focus update notification
    sockEnv = io.connect(`${location.protocol}//${location.hostname}:8000`, { transports: ['websocket'] });
    let pc;

    sockEnv.on('connect', () => {
        console.log("Env Server connected");
        // request WebRTC offer to the server
        sockEnv.emit('webrtc-offer-request');
    });
    sockEnv.on('init', (data) => {
        // data.class2color: {0: "001", ...}
        // class2color: {0: "rgba(0, 0, 255, 0.3)", ...}
        const class2color = Object.fromEntries(Object.entries(data.class2color)
            .map(([classId, colorBinStr]) => [classId, binStr2Rgba(colorBinStr)])
        );  // TODO: receive colors directly
        barColors = Object.keys(class2color).sort().map(key => class2color[key]);
        barBorderColors = barColors.map(rgba => scaleRgba(rgba, 0.7, 1));  // 70% darkened colors
        numClasses = Object.keys(class2color).length;
        const numAgents = data.numAgents;
        command = Array(numAgents).fill(null);
        nextAcceptableCommands = Array(numAgents).fill([]);
    });
    sockEnv.on('command', (data) => {
        // this event should be emitted only after the 'init' event
        const agentId = data.agentId;
        command[agentId] = data.command;
        nextAcceptableCommands[agentId] = data.nextAcceptableCommands;
        console.log(`Command of agent ${agentId} updated: ${command[agentId]}, ${nextAcceptableCommands[agentId]}`);
        updateChartColor(charts[agentId], command[agentId], nextAcceptableCommands[agentId]);
    });
    sockEnv.on('subtaskDone', (agentId) => {
        console.log(`Subtask done: ${agentId}`);
    });
    sockEnv.on('taskDone', () => {
        console.log('All tasks done');
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
        sockEEG.on('eeg', (data) => {
            // forward the command to the env server
            const command = data.command;
            sockEnv.emit('eeg', command);
            const likelihoods = data.likelihoods;
            console.log(`EEG data received:\n command ${command}\n likelihoods ${likelihoods.map(l => l.toFixed(2))}`);

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
    const config = {
        type: 'bar',
        data: {
            labels: Array(numClasses).fill(''),  // neccesary
            datasets: [{
                data: Array(numClasses).fill(0.4),
                backgroundColor: barColors,
                borderColor: barBorderColors,
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
            maintainAspectRatio: false,
            backgroundColor: 'white',
        },
    };

    // Create charts
    const chartCanvases = document.getElementsByClassName('likelihood-chart');
    [...chartCanvases].forEach((canvas) => {
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
    chart.data.datasets[0].data = likelihoods.map((likelihood, command) =>
        nextAcceptableCommands[agentId].includes(command) ? likelihood : chart.data.datasets[0].data[command]
    );
    chart.update();
}

const updateChartColor = (chart, currentCommand, nextAcceptableCommands) => {
    if (chart === undefined) return;

    const modBg = (barId) => {
        // highlight the current command bar
        if (barId === currentCommand) return scaleRgba(barColors[barId], 1, 1);
        return barColors[barId];
    }
    const modBorder = (barId) => {
        // add black border to the current command bar
        if (barId === currentCommand) return 'rgba(0, 0, 0, 1)';
        // remove border from the unacceptable command bars
        if (nextAcceptableCommands.includes(barId)) return barBorderColors[barId];
        return 'rgba(255, 255, 255, 1)';
    }
    chart.data.datasets[0].backgroundColor = [...Array(numClasses).keys()].map(modBg);
    chart.data.datasets[0].borderColor = [...Array(numClasses).keys()].map(modBorder);
    chart.update();
}
