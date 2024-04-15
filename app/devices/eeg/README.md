# EEG

The `devices/eeg/` directory contains an application for real-time decoding of EEG/EMG/ECoG data and transmitting it to the WebUI via WebSocket.  
It is executed on the user's PC.


## Components

- `main.py`
  - Launches the WebSocket server (using FastAPI).
  - Initializes the decoder and recorder.
  - Receives LabStreamingLayer (LSL) data streams and creates ReactiveX observables to pass to the decoder and recorder.

- `decoder.py`
  - Performs decoding of EEG data.
  - Uses ReactiveX for buffering, performs decoding with a model instance, and sends the results to the WebUI via WebSocket.
  - Also provides a function for measuring the baseline.

- `recorder.py`
  - Records EEG data.
  - Uses ReactiveX for buffering, records data at specified intervals and chunk sizes, and saves it to a specified path.

- `models/`
  - Provides models used for EEG decoding.
  - `threshold_model.py`
    - A simple threshold-based model.
    - Outputs the index of the channel with the highest root mean square (RMS) that exceeds the threshold as a class.
  - More models will be added here.

## Usage
- If you have an EEG device, set it up and start LSL streaming.
- If you do not have a device, run a mock EEG stream.
  ```bash
  python app/devices/eeg/mock_streamer/main.py
  ```
- Launch the server.
  ```bash
  python app/devices/eeg/main.py \
    -e <your environment server ip> \
    -u <username>  # The server will save the data to `devices/eeg/logs/<username>/<current date>/`
  ```
- Switch the "EEG" toggle in the browser to connect.
- Follow the prompt to measure the baseline.
- Real-time classification begins.
  - The results are sent to the environment and used as a subtask selection command.

### In data collection mode
- Launch the server with recorder only.
  ```bash
  python app/devices/eeg/main.py \
      -e <your environment server ip> \
      -u <username> \
      --no-decode
  ```
- Optimize the model parameters.
  ```bash
  python app/devices/eeg/train.py \
      -u <username> \
      -d <datetime>  # The date and time of the recording to train on
  ```
- Launch the server with the optimized model.
  ```bash
  python app/devices/eeg/main.py \
      -e <your environment server ip> \
      -u <username> \
      -d <datetime>  # The date and time of the model to use (same as the date of the recording)
  ```

You can also use audio signals using [LSL AudioCapture](https://github.com/labstreaminglayer/App-AudioCapture) by setting `--input Audio`.
