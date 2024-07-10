import { createCharts, resetChartData, updateChartColor, updateChartData, updateChartLock } from './chart.js';
import { getFocusId, getInteractionTime, resetInteractionTimer, setSockEnv } from './cursor.js';
import { startDataCollection, stopDataCollection } from './dataCollection.js';
import { init as initEEG, sendDataCollectionOnset } from './eeg.js';
import { init as initGamepad } from './gamepad.js';
import { init as initGaze } from './gaze.js';
import { init as initKeyboard } from './keyboard.js';
import { init as initMouse } from './mouse.js';
import { binStr2Rgba, disconnectUser, getCookie } from './utils.js';
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

let sockEnv, userinfo, commandLabels, commandColors;
let isStarted = false;  // if true, task is started and accepting subtask selection
let isDataCollection = false;

// Tracking active tabs / window
let active_tab_detected = false;

if (localStorage.getItem("active-tab")) {
    active_tab_detected = true; // Closing this tab will not remove main tab(windows)'s "active-tab" flag
    const modal = document.getElementById('active-tab-modal');
    const modalInstance = new bootstrap.Modal(modal);
    modalInstance.show();
} else {
    localStorage.setItem("active-tab", true);
};

// Notify backend when the browser window is closed
// for server-side tracking of connected users
window.addEventListener("beforeunload", (event) => {
    // TODO: what if there is no uniquer_user_id set yet ?
    let unique_user_id = getCookie("unique_user_id");
    disconnectUser(unique_user_id);
    // Negate active tab flag only if the current one is a valid one
    if (! active_tab_detected) {
        localStorage.removeItem("active-tab");
    };
});

window.addEventListener("unload", (event) => {
    let unique_user_id = getCookie("unique_user_id");
    disconnectUser(unique_user_id);
    // Negate active tab flag only if the current one is a valid one
    if (! active_tab_detected) {
        localStorage.removeItem("active-tab");
    };
});

document.addEventListener("DOMContentLoaded", async () => {
    connectEnv();

    // get userinfo
    const response = await fetch('/api/getuser');
    userinfo = await response.json();

    // buttons
    document.getElementById('start-button').addEventListener('click', () => requestServerStart());
    document.getElementById('reset-button').addEventListener('click', () => requestServerStop());

    clientReset();
});

const updateTaskStatusMsg = (msg) => {
    document.getElementById('task-status-message').innerText = msg;
}

const updateLog = (msg, numSpace = 0) => {
    const log = document.getElementById('log');
    log.textContent += ' '.repeat(numSpace) + msg + '\n';
    log.scrollTop = log.scrollHeight;
}

const requestServerStart = () => {
    document.getElementById('start-button').disabled = true;
    document.getElementById('reset-button').disabled = true;
    document.getElementById('hp-button').disabled = true; // disable during the countdown

    // request the server to start the environment
    sockEnv.emit('requestServerStart');
    // "isStart" will be set to true by "serverStartDone" event from the server
}

const onServerStartDone = () => {
    document.getElementById('reset-button').disabled = false;  // allow stop&reset
}

const clientStart = () => {
    document.getElementById('start-button').disabled = true;  // disable start button for clients who have not pressed it
    document.getElementById('hp-button').disabled = true;  // disable back to menu

    sockEnv.emit('addUser', {
        userinfo: userinfo,
        deviceSelection: JSON.parse(sessionStorage.getItem('deviceSelection')),
    }, () => {
        updateLog('User added to the environment');
    });

    if (isDataCollection) {
        document.addEventListener('dataCollectionOnset', onDataCollectionOnset);
        document.addEventListener('dataCollectionCompleted', onDataCollectionCompleted);
        // TODO: hide NASA TLX survey button in data coll mode ?
        startDataCollection(commandColors, commandLabels);
    }

    isStarted = true;  // allow subtask selection
}

// Data collection event handlers
const onDataCollectionOnset = async (event) => {
    sendDataCollectionOnset(event);  // eeg server; TODO: also for other devices?
    updateLog(`Cue: ${event.detail.cue}`);
};

const onDataCollectionCompleted = async () => {
    requestServerStop(true);
};


const requestServerStop = (isCompleted = false) => {
    document.getElementById('start-button').disabled = true;
    document.getElementById('reset-button').disabled = true;
    document.getElementById('hp-button').disabled = true;  // disable back to menu
    sockEnv.emit('requestServerStop', isCompleted);
}

const clientStop = (isCompleted = false) => {
    document.getElementById('reset-button').disabled = true;  // disable stop&reset button for clients who have not pressed it
    document.getElementById('hp-button').disabled = true;  // disable back to menu

    if (!isStarted) {
        // called by
        // - the stop&reset button during the countdown
        // - the stop&reset button after taskDone
        // - the taskStopDone event from the server after pressing the stop&reset button
        return;
    }
    isStarted = false;

    if (isDataCollection) {
        stopDataCollection();
        document.removeEventListener('dataCollectionOnset', onDataCollectionOnset);
        document.removeEventListener('dataCollectionCompleted', onDataCollectionCompleted);
    }

    if (isCompleted) {
        // Popup for repeat or back to menu
        // This ensures the expId is not reused
        const modal = document.getElementById('task-complete-modal');
        const modalInstance = new bootstrap.Modal(modal);
        modalInstance.show();
    } else {
        if (isDataCollection) location.reload();  // Force data collection recorder to restart
        else clientReset();
    }
}

const clientReset = () => {
    document.getElementById('start-button').disabled = false;
    document.getElementById('reset-button').disabled = true;
    document.getElementById('hp-button').disabled = false;
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

        sockEnv.emit('webrtc-offer-request', userinfo);
    });
    
    sockEnv.on('status', (message) => {
        updateTaskStatusMsg(message);
        updateLog(`Server: ${message}`);
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

        // Share userinfo across the session, for other modules to use
        sessionStorage.setItem("userinfo", JSON.stringify(userinfo));
    });
    sockEnv.on('command', ({ agentId, command, nextAcceptableCommands, isNowAcceptable, hasSubtaskNotDone, likelihoods, interactionTime, username}) => {
        if (interactionTime) {
            updateLog(`Agent ${agentId}: Interaction time ${interactionTime.toFixed(1)}s`);
        }
        if (!isNowAcceptable) {
            // Command was not updated because agent was already executing an action
            // Currently we do not count this as a subtask selection
            updateLog(`Agent ${agentId}: Command update failed (by "${username}")`);
            updateLog(`Agent is executing an action`, 2);
        } else if (!hasSubtaskNotDone) {
            // Command was not updated because the selected subtask has already been done
            // We consider this as an "invalid" subtask selection and count as an error
            updateLog(`Agent ${agentId}: Command update failed (by "${username}")`);
            updateLog(`Task "${command}" is already done`, 2);
            console.assert(command !== '', 'empty command');
        } else {
            // Command was valid and updated
            if (command !== '') {
                updateLog(`Agent ${agentId}: Command updated to "${command}" by "${username}"`);
                if (likelihoods !== null) updateChartData(agentId, likelihoods);  // sync the chart data before updating the lock status
            }
            updateChartLock(agentId, nextAcceptableCommands);
            updateChartColor(agentId, command, username);
        }
    });
    sockEnv.on('requestClientStart', clientStart);
    sockEnv.on('serverStartDone', onServerStartDone);
    sockEnv.on('requestClientStop', clientStop);
    sockEnv.on('subtaskDone', ({ agentId, subtask }) => {  // TODO: subtaskCompleted
        updateLog(`Agent ${agentId}: Subtask "${subtask}" done`);
        if (getFocusId() === agentId) resetInteractionTimer();  // reset the timer if the agent is selected so that the time during the subtask is not counted
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

    // Update the connected user names when the Python side sends and update
    // TODO: make the connect user list updated based on the mode
    sockEnv.on('userListUpdate', async (user_list) => {
        userinfo.user_list = user_list; // TODO: is this actually needed ?
        const usernameAreaDiv = document.getElementById('username-area');
        if (userinfo.user_list && userinfo.user_list.length > 0) {
            var userListContent = "";
            user_list.forEach(connectUserName => {
                if (connectUserName == userinfo.name) {
                    userListContent += `<b><i>${connectUserName}</i></b><br/>`;
                } else {
                    userListContent += `${connectUserName}<br/>`;
                };
            });
            usernameAreaDiv.innerHTML = userListContent;
        } else {
            usernameAreaDiv.innerHTML = 'No users available';
        };
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
            userinfo: userinfo,
        });
    }
    // update the chart
    updateChartData(agentId, likelihoods);
}
