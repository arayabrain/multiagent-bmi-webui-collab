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

## Keyboard Controls

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

## References and Citations
Initial Robot Arm HRI Benchmarking paper: [A Multi-User Multi-Robot Multi-Goal Multi-Device Human-Robot Interaction Manipulation Benchmark](https://www.frontiersin.org/journals/robotics-and-ai/articles/10.3389/frobt.2025.1528754/abstract)
Please cite it as:
```
@article{yoshida2025m4bench,
	author={Yoshida, Akito and Dossa, Rousslan Fernand Julien and Di Vincenzo, Marina and Sujit, Shivakanth and Douglas, Hannah and Arulkumaran, Kai},
	title={A Multi-User Multi-Robot Multi-Goal Multi-Device Human-Robot Interaction Manipulation Benchmark},
	journal={Frontiers in Robotics and AI},
	volume={12},
	year={2025},
	url={https://www.frontiersin.org/journals/robotics-and-ai/articles/10.3389/frobt.2025.1528754/abstract},
	doi={10.3389/frobt.2025.1528754}
}
```

## Acknowledgments

This system extends work by **Araya Inc.** and the **Yanagisawa Lab, Osaka University** for real-time control of robotic systems via BMI interfaces.

## License

This project is based on collaborative research and is intended for academic and educational use only.
