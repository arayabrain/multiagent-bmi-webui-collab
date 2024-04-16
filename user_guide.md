**Robot Environment Server Setup**
- Open a terminal and SSH connect to the server that runs the robot environment
  ```bash
  ssh vector  # IP address: 10.10.0.137
  ```
- Start the environment
  ```bash
  cd path/to/multiagent-bmi-webui
  python app/main.py
  ```

**Data Collection Mode**
- Access the web interface for data collection mode via a browser
  - https://10.10.0.137:8000/data-collection
  - Enter username (`user1`)
  ![Data collection mode UI](assets/ui_data_collection.png)
- Open a terminal and start the EEG recorder
  ```bash
  python app/devices/eeg/main.py -e 10.10.0.137 --no-decode -u user1
  ```
- Turn on the "EEG/EMG" toggle switch in the browser
  - (The recorder connects to the browser)
- When a prompt to start baseline measurement appears in the terminal, press Enter to begin measurement
  ![Recorder prompt](assets/recorder_prompt.png)
- In the browser, press the "Start" button and follow the cues to input signals
- When "Completed!" appears,
  - Press "Stop&Reset",
  - Turn off the "EEG/EMG" toggle switch,
  - End the EEG recorder with Ctrl+C

**Model Training**
- Run train.py
  ```bash
  python app/devices/eeg/train.py -u user1 -d YYYYMMDD_HHMMSS
  ```
  - `-d`: date of the recorder's saved data `devices/logs/user1/YYYYMMDD_HHMMSS/recording.hdf5`

**Task**
- Access the web interface via a browser
  - https://10.10.0.137:8000
  - Enter username (`user1`)
  ![Task mode UI](assets/ui_task.png)
- (If necessary, set up a robot selection device and turn on the toggle switch in the browser)
- Open a terminal and start the EEG decoder & recorder
  ```bash
  python app/devices/eeg/main.py -e 10.10.0.137 -u user1 -d YYYYMMDD_HHMMSS
  ```
  - Use `--no-record` if you do not wish to record
- Turn on the "EEG/EMG" toggle switch in the browser
- When a prompt to start baseline measurement appears in the terminal, press Enter to begin measurement
- Execute the task
- When "Completed!" appears,
  - Press "Stop&Reset",
  - Turn off the "EEG/EMG" toggle switch,
  - End the EEG decoder & recorder with Ctrl+C