# Experimental Log Analysis

English | [简体中文](README%20(1)_zh.md)

Calibration, noise and frequency-response analysis for compatible measurement logs.

Archived project retained for reference.

## Overview

`analyze_data.py` parses measurement and calibration records, estimates noise and uncertainty, and can write plots and a Markdown report. Demonstration data is synthetic.

## Technology and Dependencies

Python 3, NumPy and Matplotlib; a CJK font for Chinese plot labels.

## Repository Structure

`analyze_data.py`, `sim_system.py`, technical notes and saved outputs.

## Quick Start

```bash
python -m pip install numpy matplotlib
python analyze_data.py --demo
python analyze_data.py path/to/log.txt --plot-dir plots --report report.md
```

The eight CSV columns are `t_ms, V1_mV, V2_mV, P, x_mm, I_nA, U_nV, f_Hz`. Optional `--params`, `--truth` and `--freq-list` inputs configure device parameters and comparisons; see `--help`.
