# multiagent-bmi-webui
Web UI for the multi-agent robot arm environment

## Overview
![overview image](assets/overview.png)


## Installation
1. Create and activate a virtual environment. Tested with Python 3.10.
2. Install [robohive](https://github.com/dosssman/robohive/tree/multi-robot)
    (If you use the `custom_robohive_design` environment, the original robohive may also work, but it's not verified)
    ```bash
    git clone --recursive https://github.com/dosssman/robohive.git
    cd robohive
    git checkout multi-robot
    pip install -e .
    ```
3. Install [custom_robohive_design](https://github.com/shivakanthsujit/custom_robohive_design) (Ask Shiva to add you to collaborators)
    ```bash
    git clone https://github.com/shivakanthsujit/custom_robohive_design.git
    cd custom_robohive_design
    git checkout use-from-webui  # temporary
    pip install -e .
    ```
3. Clone this repository
4. Install
    ```bash
    # server only
    pip install -e .[server]
    # user only
    pip install -e .[user]
    # both
    pip install -e .[server,user]
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
    - `FrankaPickPlaceMulti-v0` in `custom_robohive_design/env_init.py`


## Run
Activate your virtual environment, then:
1. Run environment server:
    ```bash
    python app/main.py
    ```
    and open `http://${server ip}:8000/` in your browser.
2. Pupil Core
    - If you have the device
        1. set it up and run Pupil Capture
        2. Run Pupil Core websocket server:
            ```
            python app/devices/pupil.py
            ```
    - If you don't have the device, run dummy one:
        ```bash
        python app/devices/pupil_dummy.py
        ```
    - Toggle the "Eye Tracker" switch on the browser.
      The red frame should move according to the position of your gaze.
3. EEG/EMG
    - If you have the device, set it up and start LSL streaming
    - If you don't have the device, run the mock EEG stream
        (there is only one channel currently)
        ```bash
        python app/devices/mock_streamer/eeg.py
        ```
    - Run the decoder script
        ```bash
        python app/devices/eeg.py
        ```
    - Toggle the "EEG" switch on the browser.
    - Perform baseline measurements according to the prompt.
    - The classification results are then sent to the environment and used as commands for the focused robot.

    You can use audio signals using [LSL AudioCapture](https://github.com/labstreaminglayer/App-AudioCapture). Set `--input Audio` and adjust the decoder threshold e.g. `--thres 5`.

    [!WARNING]
    The correspondence between the command and the robot's target is currently being worked out.
