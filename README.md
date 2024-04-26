# multiagent-bmi-webui
Web UI for the multi-agent robot arm environment

## Overview
![web interface image](assets/web_interface.png)

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
    IP.2 = <your server ip>
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
Also check the network settings of your anti-virus software.

- You may need to comment out `max_episode_steps` of the environment you use to remove the episode time limit.
    - `FrankaPickPlaceSingle4Col-v1` in `robohive_multi/envs/single_arms/__init__.py`
    - `FrankaPickPlaceMulti4Robots4Col-v1` in `robohive_multi/envs/multi_arms/__init__.py`


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
        - Please see the [README](app/devices/eye/README.md).
3. Run devices for selecting commands
    - Keyboard
        - Use the number keys (1, 2, 3, 4) to enter commands.
    - EEG/EMG
        - Please see the [README](app/devices/eeg/README.md).

(TODO: update on data-collection mode)
