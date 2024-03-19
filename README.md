# multiagent-bmi-webui
Web UI for the multi-agent robot arm environment

## Overview
![overview image](assets/overview.png)


## Installation
1. Create and activate a virtual environment. Tested with Python 3.10.
2. Install [robohive-multi](https://github.com/arayabrain/robohive-multi) companion repository.
This might require getting reading permission to the repository.

    ```bash
    git clone --recurse-submodules -j8 \
    git@github.com:arayabrain/robohive-multi.git
    pip install -e robohive-multi/.
    pip install -e robohive-multi/robohive/.
    pip install -e robohive-multi/vtils/.
    ```

3. Clone this repository
4. Install
    ```bash
    # server only
    pip install -e '.[server]'
    # user only
    pip install -e '.[user]'
    # both
    pip install -e '.[server,user]'
    ```
5. (If you launch a server) Generate a self-signed certificate for the server  
    If you're using a machine other than `localhost` (the same machine to start the UI/browser) as the server, please add the IP to `.keys/san.cnf`.
    ```cnf
    [ alt_names ]
    IP.1 = 127.0.0.1  # localhost
    IP.2 = 10.10.0.137  # vector
    IP.3 = <your server ip>
    ```
    Then run the following commands to generate the certificate and keys:
    ```bash
    cd .keys
    openssl req -new -nodes -out server.csr -keyout server.key -config san.cnf
    openssl x509 -req -days 365 -in server.csr -signkey server.key -out server.crt -extensions req_ext -extfile san.cnf
    ```

- On Linux, you need to install `liblsl` to use the [LSL](https://github.com/sccn/liblsl).
    Choose the appropriate version for your OS in the [release page](https://github.com/sccn/liblsl/releases) and then
    ```bash
    wget https://github.com/sccn/liblsl/releases/download/v1.16.2/liblsl-1.16.2-focal_amd64.deb  # change to the appropriate one
    sudo apt install libpugixml1v5  # dependencies
    sudo dpkg -i liblsl-1.16.2-focal_amd64.deb
    ```

- On windows, you need to open ports for the WebRTC UDP communication.
Open Windows Firewall settings (`wf.msc`) and create a new inbound rule to allow UDP ports `49152-65535`.

- You may need to comment out `max_episode_steps` of the environment you use to remove the episode time limit.
    - `FrankaReachFixedMulti-v0` in `robohive/envs/arms/__init__.py`
    - `FrankaPickPlaceMulti4-v0` in `custom_robohive_design/env_init.py`


## Run
Activate your virtual environment, then:
1. Run environment server:
    ```bash
    python app/main.py
    ```
    and open `https://${server ip}:8000/` in your browser.  
    You will see a warning because we are using a self-signed certificate, but please ignore it and proceed with the connection.
2. Run devices for selecting a robot to control  
    You can select a robot that by moving the cursor using various devices.
    - Mouse
    - Gamepad
    - Pupil Core
        - If you have the device,
            1. set it up and run Pupil Capture
            2. Run gaze websocket server:
                ```bash
                python app/devices/pupil.py \
                    [-e <your environment server ip> (default: localhost)]
                ```
        - If you don't have the device, run dummy one:
            ```bash
            python app/devices/pupil_dummy.py \
                [-e <your environment server ip> (default: localhost)]
            ```
        Toggle the "Eye Tracker" switch on your browser.
3. Run devices for selecting commands
    - Keyboard
        Use the number keys to enter commands.
    - EEG/EMG
        - If you have the device, set it up and start LSL streaming
        - If you don't have the device, run the mock EEG stream
            (there is only one channel currently)
            ```bash
            python app/devices/mock_streamer/eeg.py
            ```
        - Run the decoder script
            ```bash
            python app/devices/eeg.py \
                [-e <your environment server ip> (default: localhost)] \
                [-p <recorded data path> (default: logs/data.hdf5)]
            ```
        Toggle the "EEG" switch on your browser.  
        Then follow the prompts to take a baseline measurement.  
        The classification results are then sent to the environment and used as commands for the focused robot.  

        You can also use audio signals using [LSL AudioCapture](https://github.com/labstreaminglayer/App-AudioCapture). Set `--input Audio` and adjust the decoder threshold e.g. `--thres 5`.

### List of commands
- None: no command
- 0: cancel manipulation (key `0`)
- 1: manipulate target 1 (key `1`)
- 2: manipulate target 2 (key `2`)
- 3: manipulate target 3 (key `3`); currently not used
