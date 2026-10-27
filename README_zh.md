# WeakSignal

[English](README.md) | 简体中文

用于光杠杆放大微弱电信号测量的 Arduino 程序与 Python 分析工具。

归档项目，保留用于参考。

## 项目概述

项目围绕线圈偏转、光杠杆放大、位置敏感探测器（PSD）读出、ADC 采样和标定展开，包含独立 Arduino 程序、电路设计、演示代码及仿真与实验日志分析工具。

`src/code/` 保存原有硬件程序；`src/ClawsGo/` 保存技术审查与分析工作，其旧说明中提到的数据采集、低频信号源固件并未出现在该目录。仿真数值取决于模型参数，不能作为装置实测性能。`src/ref/` 为外部参考资料。

## 技术栈与依赖

- Arduino C/C++、Arduino IDE 和兼容开发板。
- 标定和测量程序使用 Adafruit ADS1X15；原 FM 信号源使用 Adafruit Si4713，并需安装库管理器提示的依赖。
- Python 3、NumPy、Matplotlib；可选音频信号脚本另需 `sounddevice` 和可用音频后端。
- 硬件示例涉及 ADS1115、PSD 与模拟调理电路，具体依程序而定。查看电路文件可使用 Fritzing。

## 文件结构

```text
src/code/       信号源、电流源、标定和测量程序
src/ClawsGo/    Python 仿真、日志分析与技术审查
src/demo/       演示程序及装置素材
src/fritzing/   电路图与 Fritzing 元件
src/ref/        外部参考资料
v1/            早期方案文档与代码
```

## 快速上手

在仓库根目录运行无需硬件的分析示例：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install numpy matplotlib
cd src/ClawsGo
python analyze_data.py --demo
```

使用 `python analyze_data.py path/to/log.txt --plot-dir plots --report report.md` 分析兼容日志。运行 `python sim_system.py` 执行固定参数仿真，按实际装置修改脚本常量；图中文字可能需要系统中文字体。

硬件部分：在 Arduino IDE 中打开 `src/code/` 下的一个程序，安装对应库，核对引脚、板型和端口后上传，串口波特率为 115200。先标定，再将拟合系数写入测量程序。原 Si4713 射频信号源与低频测量改进方案属于不同路线，组合使用前应核对技术审查说明。
