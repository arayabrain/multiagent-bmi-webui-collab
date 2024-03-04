import { getFocusId, setSockEnv, updateAndNotifyFocus, updateCursorAndFocus } from './cursor.js';
import { setGamepadHandler } from './gamepad.js';
import { binStr2Rgba, scaleRgba } from './utils.js';
import { handleOffer, handleRemoteIce, setupPeerConnection } from './webrtc.js';

let sockEnv, sockGaze, sockEEG;
let videos, toggleGaze, toggleEEG, aprilTags;
let class2color, numClasses, numAgents;  // info from the env server
const charts = [];

document.addEventListener("DOMContentLoaded", () => {
    videos = document.querySelectorAll('video');
    toggleGaze = document.getElementById('toggle-gaze');
    toggleEEG = document.getElementById('toggle-eeg');
    aprilTags = document.getElementsByClassName("apriltag");

    connectEnv();

    toggleGaze.addEventListener('change', () => {
        if (toggleGaze.checked) {
            updateConnectionStatus('connecting', 'toggle-gaze');
            sockGaze = io.connect(`http://localhost:8001`, { transports: ['websocket'] });  // TODO: https?
            sockGaze.on('connect', () => {
                updateConnectionStatus('connected', 'toggle-gaze');
                console.log("Gaze server connected");
            });
            sockGaze.on('disconnect', () => {
                updateConnectionStatus('disconnected', 'toggle-gaze');
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
    });

    toggleEEG.addEventListener('change', () => {
        if (toggleEEG.checked) {
            updateConnectionStatus('connecting', 'toggle-eeg');
            sockEEG = io.connect(`http://localhost:8002`, { transports: ['websocket'] });  // TODO: https?
            sockEEG.on('connect', () => {
                sockEEG.emit('init', { numClasses: numClasses });
                updateConnectionStatus('connected', 'toggle-eeg');
                console.log("EEG server connected");
            });
            sockEEG.on('disconnect', () => {
                updateConnectionStatus('disconnected', 'toggle-eeg');
                console.log("EEG server disconnected");
            });
            sockEEG.on('reconnect_attempt', () => {  // TODO: not working
                console.log("EEG server reconnecting...");
            });
            sockEEG.on('init', (data) => {
                createCharts(data.threshold);
            });
            sockEEG.on('eeg', (arrayBuffer) => {
                const view = new DataView(arrayBuffer);
                const command = view.getUint8(0, true);
                const likelihoods = new Float32Array(arrayBuffer.slice(1));
                console.log(`EEG data received:\n command ${command}\n likelihoods ${Array.from(likelihoods).map(l => l.toFixed(2))}`);
                sockEnv.emit('eeg', command);

                const focusId = getFocusId();
                if (focusId == null || charts.length == 0) return;
                updateChartData(charts[focusId], likelihoods);
            });
        } else {
            if (sockEEG.connected) sockEEG.disconnect();
            removeCharts(charts);
        }
    });

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
        );
        numClasses = Object.keys(class2color).length;
        numAgents = data.numAgents;
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


const showAprilTags = () => {
    Array.from(aprilTags).forEach((tag) => {
        tag.style.display = 'block';
    });
}

const hideAprilTags = () => {
    Array.from(aprilTags).forEach((tag) => {
        tag.style.display = 'none';
    });
}


const updateConnectionStatus = (status, elementId) => {
    var statusElement = document.getElementById(elementId);
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
    chart.data.datasets[0].data = data;
    chart.update();
}
