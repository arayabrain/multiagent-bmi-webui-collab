# app/bci_input.py

import time
from pylsl import StreamInlet, resolve_stream
from app.bci.bci_decoder import decode_bci_signal
import asyncio
import websockets

# ---- Config
WS_URL = "ws://localhost:8000/ws/control"

# ---- Connect to LSL Stream
print("Searching for EEG stream...")
streams = resolve_stream('type', 'EEG')
inlet = StreamInlet(streams[0])
print("EEG stream connected!")

# ---- Send decoded actions to WebSocket
async def send_actions():
    async with websockets.connect(WS_URL) as websocket:
        print("Connected to WebSocket server.")

        while True:
            sample, _ = inlet.pull_sample()
            action = decode_bci_signal(sample)
            await websocket.send(action)
            print(f"Sent action: {action}")
            await asyncio.sleep(0.1)  # Throttle for ~10 Hz

# ---- Run it
if __name__ == "__main__":
    asyncio.run(send_actions())
