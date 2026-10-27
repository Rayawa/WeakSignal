# Analysis Tools

English | [简体中文](README_zh.md)

Python tools and review notes for optical lever measurement models.

Archived project retained for reference.

## Overview

This directory contains `analyze_data.py` for compatible CSV logs and `sim_system.py` for a fixed-parameter simulation. Earlier notes describe firmware that is not included here; the original hardware sketches are in `../code/`. Model predictions require experimental validation.

## Technology and Dependencies

Python 3, NumPy and Matplotlib; a CJK font for Chinese plot labels.

## Repository Structure

`analyze_data.py`, `sim_system.py`, technical notes and saved outputs.

## Quick Start

```bash
python -m pip install numpy matplotlib
python analyze_data.py --demo
python sim_system.py
```

The analysis log columns are `t_ms, V1_mV, V2_mV, P, x_mm, I_nA, U_nV, f_Hz`. Run `python analyze_data.py --help` for supported options. Simulation constants are defined in the source; its current version has no configuration CLI.
