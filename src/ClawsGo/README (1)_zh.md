# 实验日志分析

[English](README%20(1).md) | 简体中文

兼容测量日志的标定、噪声与频率响应分析。

归档项目，保留用于参考。

## 项目概述

`analyze_data.py` 解析测量和标定记录，估算噪声及不确定度，并可输出图件和 Markdown 报告。演示数据由程序生成。

## 技术栈与依赖

Python 3、NumPy、Matplotlib；中文图件需要可用中文字体。

## 文件结构

`analyze_data.py`、`sim_system.py`、技术说明及保存的输出。

## 快速上手

在本目录安装依赖并执行下列对应命令；其他参数以 `python analyze_data.py --help` 为准。

```bash
python -m pip install numpy matplotlib
python analyze_data.py --demo
python analyze_data.py path/to/log.txt --plot-dir plots --report report.md
```
