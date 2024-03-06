import { getFocusId, setSockEnv, updateAndNotifyFocus, updateCursorAndFocus } from './cursor.js';
import { setGamepadHandler } from './gamepad.js';
import { binStr2Rgba, scaleRgba } from './utils.js';
import { handleOffer, handleRemoteIce, setupPeerConnection } from './webrtc.js';

let sockEnv, sockGaze, sockEEG;
let videos, toggleGaze, toggleEEG, aprilTags;
let class2color, numClasses, command;  // info from the env server
const charts = [];

document.addEventListener("DOMContentLoaded", () => {
    videos = document.querySelectorAll('video');
    toggleGaze = document.getElementById('toggle-gaze');
    toggleEEG = document.getElementById('toggle-eeg');
    aprilTags = document.getElementsByClassName("apriltag");

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
        class2color = Object.fromEntries(Object.entries(data.class2color)
            .map(([classId, colorBinStr]) => [classId, binStr2Rgba(colorBinStr)])
        );  // TODO: receive colors directly
        numClasses = Object.keys(class2color).length;
    });
    sockEnv.on('command', (data) => {
        command = data;
        console.log("SockEnv: command ", command);
        if (charts.length > 0) {
            const focusId = getFocusId();
            toggleChartActivationIfNeeded(charts[focusId], command[focusId]);
        }
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

const onToggleGaze = (checked) => {
    if (checked) {
        updateConnectionStatusElement('connecting', 'toggle-gaze');
        sockGaze = io.connect(`http://localhost:8001`, { transports: ['websocket'] });  // TODO: https?
        sockGaze.on('connect', () => {
            updateConnectionStatusElement('connected', 'toggle-gaze');
            console.log("Gaze server connected");
        });
        sockGaze.on('disconnect', () => {
            updateConnectionStatusElement('disconnected', 'toggle-gaze');
            console.log("Gaze server disconnected");
        });
        sockGaze.on('reconnect_attempt', () => {  // TODO: not working
            console.log("Gaze server reconnecting...");
        });
        sockGaze.on('gaze', (data) => {
            console.log("Gaze data received: ", data);
            updateAndNotifyFocus(data.focusId);
        });
        showAprilTags();
    } else {
        if (sockGaze.connected) sockGaze.disconnect();
        hideAprilTags();
    }
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
            updateChartData(charts[focusId], likelihoods);
        });
    } else {
        if (sockEEG.connected) sockEEG.disconnect();
        removeCharts(charts);
    }
}

const showAprilTags = () => {
    [...aprilTags].forEach((tag) => {
        tag.style.display = 'block';
    });
}

const hideAprilTags = () => {
    [...aprilTags].forEach((tag) => {
        tag.style.display = 'none';
    });
}


const updateConnectionStatusElement = (status, statusElementId) => {
    var statusElement = document.getElementById(statusElementId);
    statusElement.classList.remove('connected', 'disconnected', 'connecting');
    switch (status) {
        case 'connected':
            statusElement.classList.add('connected');
            break;
        case 'disconnected':
            statusElement.classList.add('disconnected');
            break;
        case 'connecting':
            statusElement.classList.add('connecting');
            break;
        default:
            console.error("Unknown status: ", status);
    }
}

const createCharts = (thres) => {
    if (class2color === undefined) console.error("class2color is not defined");
    const colors = Object.keys(class2color).sort().map(key => class2color[key]);
    const borderColors = colors.map(rgba => scaleRgba(rgba, 0.7, 1));  // 70% darkened colors

    const config = {
        type: 'bar',
        data: {
            labels: Array(numClasses).fill(''),  // neccesary
            datasets: [{
                data: Array(numClasses).fill(0.4),
                backgroundColor: colors,
                borderColor: borderColors,
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
            status: 'all',  // 'all' | 'cancel-only' | 'none'
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

const updateChartData = (chart, data) => {
    if (chart === undefined) return;

    if (chart.options.status === 'none') {
        return;
    } else if (chart.options.status === 'cancel-only') {
        // update only class 0
        chart.data.datasets[0].data[0] = data[0];
    } else {
        chart.data.datasets[0].data = data;
    }
    chart.update();
}

const toggleChartActivationIfNeeded = (chart, currentCommand) => {
    const commandStatus = currentCommand === null ? 'all' : currentCommand === 0 ? 'none' : 'cancel-only';
    if (chart.options.status === commandStatus) return;

    chart.options.status = commandStatus;
    const colors = Object.keys(class2color).sort().map(key => class2color[key]);
    const borderColors = colors.map(rgba => scaleRgba(rgba, 0.7, 1));

    const commands = [...Array(numClasses).keys()];
    const acceptableCommands = currentCommand === null ? commands : currentCommand === 0 ? [] : [0];

    const modBg = (command) => {
        if (command === currentCommand) return scaleRgba(colors[command], 1, 1);
        // if (acceptableCommands.includes(command)) return colors[command];
        return colors[command];
    }
    const modBorder = (command) => {
        if (command === currentCommand) return 'rgba(0, 0, 0, 1)';
        if (acceptableCommands.includes(command)) return borderColors[command];
        return 'rgba(255, 255, 255, 1)';
    }
    chart.data.datasets[0].backgroundColor = commands.map((command) => modBg(command, currentCommand));
    chart.data.datasets[0].borderColor = commands.map((command) => modBorder(command, currentCommand));

    // if (commandStatus === 'all') {
    //     // activate chart
    //     chart.data.datasets[0].backgroundColor = colors;
    //     chart.data.datasets[0].borderColor = borderColors;
    //     // chart.canvas.parentElement.style.opacity = 0.8;
    // } else if (commandStatus === 'none') {
    //     // deactivate chart
    //     chart.data.datasets[0].backgroundColor = colors.map((color, i) => i === command ? scaleRgba(color, 1, 1) : scaleRgba(color, 1, 0.1));
    //     // chart.data.datasets[0].borderColor = borderColors.map((color, i) => i == command ? color : 'rgba(0, 0, 0, 1)');
    //     chart.data.datasets[0].borderColor = colors;  // remove border
    //     // chart.canvas.parentElement.style.opacity = 0.4;
    // } else if (commandStatus === 'cancel-only') {
    //     // deactivate all but class 0 and the command class
    //     chart.data.datasets[0].backgroundColor = colors.map((color, i) => i == 0 ? color : i == command ? scaleRgba(color, 1, 1) : scaleRgba(color, 1, 0.1));
    //     // chart.data.datasets[0].borderColor = borderColors.map((color, i) => [command, 0].includes(i) ? color : 'rgba(0, 0, 0, 1)');
    //     chart.data.datasets[0].borderColor = borderColors.map((color, i) => i == 0 ? color : colors[i]);  // remove border
    //     // chart.canvas.parentElement.style.opacity = 0.8;
    // }

    chart.update();
}
