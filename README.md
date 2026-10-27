# WeakSignal

English | [简体中文](README_zh.md)

Arduino sketches and Python analysis tools for weak electrical signal measurement using optical lever amplification.

Archived project retained for reference.

## Overview

The project explores a measurement chain from coil deflection and optical lever amplification to position-sensitive detector (PSD) readout, ADC sampling and calibration. It includes separate Arduino sketches, circuit designs, demonstration code and Python tools for simulated data and experimental logs.

`src/code/` contains the original hardware sketches. `src/ClawsGo/` contains review and analysis work; the acquisition and low-frequency source firmware described in older notes is not present in that directory. Simulation outputs describe model assumptions and do not establish measured device performance. Materials in `src/ref/` are external references.

## Technology and Dependencies

- Arduino C/C++, Arduino IDE and compatible Arduino hardware.
- Adafruit ADS1X15 for the ADS1115 calibration/measurement sketches; Adafruit Si4713 for the original FM-source sketch, plus their Library Manager dependencies.
- Python 3, NumPy and Matplotlib for analysis and simulation; `sounddevice` and a working audio backend for the optional audio-source script.
- Hardware examples use an ADS1115, a PSD and analog conditioning; requirements vary by sketch. Fritzing is optional for circuit files.

## Repository Structure

```text
src/code/       Arduino signal, current, calibration and measurement sketches
src/ClawsGo/    Python simulation, log analysis and technical review notes
src/demo/       Demonstration sketches and device media
src/fritzing/   Circuit diagrams and Fritzing components
src/ref/        External reference material
v1/            Earlier design documents and code
```

## Quick Start

For a hardware-free analysis example, run from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install numpy matplotlib
cd src/ClawsGo
python analyze_data.py --demo
```

Analyze a compatible log with `python analyze_data.py path/to/log.txt --plot-dir plots --report report.md`. Run `python sim_system.py` for the fixed-parameter simulation; edit its constants to match the device. A CJK font may be needed for plot labels.

For hardware, open one sketch under `src/code/` in Arduino IDE, install its libraries, check its pin definitions, select the board and serial port, and upload. Use a 115200-baud serial monitor. Run calibration before measurement and transfer the fitted coefficients to the measurement sketch. The original Si4713 RF source and the proposed low-frequency measurement design are distinct approaches; check the technical review before combining them.
