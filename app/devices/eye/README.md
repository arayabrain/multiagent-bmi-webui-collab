# Eye Tracker

The `devices/eye/` directory contains an application for real-time gaze tracking and transmitting it to the WebUI via WebSocket.  
It is executed on the user's PC.

## Usage
- Set up your eye tracker
  - If you have the Pupil Core device:
      - set it up and run Pupil Capture
      - Run the gaze tracking server:
          ```bash
          python app/devices/eye/main.py \
              [-e <your environment server ip> (default: localhost)]
          ```
  - If you don't have the device, run a dummy gaze tracking server:
      ```bash
      python app/devices/eye/main_dummy.py \
          [-e <your environment server ip> (default: localhost)]
      ```
- See [user_guide.md](../../user_guide.md) for instructions on how to use the WebUI.
- When you move your gaze, the cursor on the browser will follow it. Placing the cursor over a camera image selects the corresponding robot, and any subtask selection commands you send will be directed to that robot.
