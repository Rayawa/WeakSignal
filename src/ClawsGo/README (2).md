# System Simulation

English | [简体中文](README%20(2)_zh.md)

A fixed-parameter Python model of the optical lever measurement chain.

Archived project retained for reference.

## Overview

`sim_system.py` models calibration, coil response, mechanical bandwidth, noise and uncertainty. It uses constants declared in the script and writes results and plots. Its current implementation does not accept `--config`, `--tag` or `--list-params`.

## Technology and Dependencies

Python 3, NumPy and Matplotlib; a CJK font for Chinese plot labels.

## Repository Structure

`analyze_data.py`, `sim_system.py`, technical notes and saved outputs.

## Quick Start

```bash
python -m pip install numpy matplotlib
python sim_system.py
```

Inspect and edit the source constants before interpreting results for a physical device. Generated figures and numerical estimates are simulation outputs.
