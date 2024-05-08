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
- Set up your EEG device
  - If you have an EEG device, set it up and start LSL streaming.
  - If you do not have a device, run a mock EEG stream.
    ```bash
    python app/devices/eeg/mock_streamer/main.py
    ```
- See [user_guide.md](../../user_guide.md) for instructions on how to use the WebUI.
