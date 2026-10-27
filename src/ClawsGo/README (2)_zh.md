# 系统仿真

[English](README%20(2).md) | 简体中文

光杠杆测量链路的固定参数 Python 模型。

归档项目，保留用于参考。

## 项目概述

`sim_system.py` 模拟标定、线圈响应、机械带宽、噪声与不确定度，并输出结果和图件。当前实现通过源码常量配置，不支持 `--config`、`--tag` 或 `--list-params`。

## 技术栈与依赖

Python 3、NumPy、Matplotlib；中文图件需要可用中文字体。

## 文件结构

`analyze_data.py`、`sim_system.py`、技术说明及保存的输出。

## 快速上手

在本目录安装依赖并执行下列对应命令；其他参数以 `python analyze_data.py --help` 为准。

```bash
python -m pip install numpy matplotlib
python sim_system.py
```
