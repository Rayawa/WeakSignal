# 分析工具

[English](README.md) | 简体中文

光杠杆测量模型的 Python 工具与审查说明。

归档项目，保留用于参考。

## 项目概述

本目录包含兼容 CSV 日志分析工具 `analyze_data.py` 与固定参数仿真 `sim_system.py`。旧说明中的固件未收录于此，原硬件程序在 `../code/`。模型预测需要实验验证。

## 技术栈与依赖

Python 3、NumPy、Matplotlib；中文图件需要可用中文字体。

## 文件结构

`analyze_data.py`、`sim_system.py`、技术说明及保存的输出。

## 快速上手

在本目录安装依赖并执行下列对应命令；其他参数以 `python analyze_data.py --help` 为准。

```bash
python -m pip install numpy matplotlib
python analyze_data.py --demo
python sim_system.py
```
