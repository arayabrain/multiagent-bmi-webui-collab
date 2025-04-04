# Multiagent BMI Controller 

A custom keyboard- and brain-control-ready interface for the [multiagent-bmi-webui-collab](https://github.com/arayabrain/multiagent-bmi-webui-collab) robot simulation environment.

This repository contains extensions to control simulated robot arms using intuitive `WASD` keyboard input or brain-computer interface (BCI/BMI) signals.

---

## Features

- Real-time robot control via keyboard (W/A/S/D + 1–4)
- WebSocket-based architecture for high-speed interaction
- Designed for easy replacement with BMI/EEG decoders
- Preserves original UI and simulation design
- Works for both single-arm and multi-arm setups

---

## Getting Started

### 1. Clone the repo
```bash
git clone https://github.com/OzgurEgeAydogan1/multiagent-bmi-controller.git
cd multiagent-bmi-controller
```

### 2. Setup Python environment (Micromamba recommended)
```bash
micromamba create -n multiagent python=3.8 -y
micromamba activate multiagent
pip install -r requirements.txt
```

### 3. Run the simulation
```bash
cd C:\Users\oegea\multiagent-bmi-webui-collab
python -m app.main
```

Then open your browser at: [https://127.0.0.1:8000](https://127.0.0.1:8000)

---

## ⌨️ Keyboard Controls

| Key | Action |
|-----|--------|
| W / A / S / D | Move robot in XY plane |
| Q / E         | Move up / down (Z axis) |
| 1 / 2 / 3 / 4 | Select red, blue, green, yellow cubes |

---

## Sample BMI Decoder Stub (EEG Integration)

We've added a placeholder decoder for imagined movement / motor imagery:

```python
# app/bci/bci_decoder.py

def decode_bci_signal(raw_signal):
    """
    Replace this with your real BCI decoder logic.
    For now, returns fixed keycode for 'W'.
    """
    return 'w'  # Simulate forward motion
```

You can plug this into the control loop to replace keyboard input with live brain signal predictions.

---

## Acknowledgments

This system extends work by **Araya Inc.** and the **Yanagisawa Lab, Osaka University** for real-time control of robotic systems via BMI interfaces.
