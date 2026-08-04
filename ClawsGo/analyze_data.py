# -*- coding: utf-8 -*-
"""
实验数据分析工具 —— 微弱电信号测量系统
========================================
读取 Arduino 串口日志（data_acquisition.ino 的 CSV 输出）与标定输出，
完成：数据解析、后级标定拟合、盲测校验、噪声底与探测极限、平均时间优化、
频率响应、GUM 不确定度预算，并输出图件与 Markdown 报告。

用法
----
  # 分析一份串口日志（自动识别标定段/测量段）
  python3 analyze_data.py 串口日志.txt [--plot-dir 输出图目录] [--report 报告.md]

  # 生成示例日志并跑通全流程（无需硬件，用于熟悉工具与验证流程）
  python3 analyze_data.py --demo

  # 频率响应测试需要给出各段的驱动频率（按时间顺序与段一一对应）
  python3 analyze_data.py 日志.txt --freq-list "0.05,0.1,0.2,0.3,0.5,1.0"

  # 盲测偏差分析：--truth 文件给出各段真实电流(µA)，与测量值对比
  python3 analyze_data.py 日志.txt --truth truth.csv

  # 用装置实际参数覆盖设计默认值（与仿真参数化共用同一 JSON 格式）
  python3 analyze_data.py 日志.txt --params device.json

串口日志格式（data_acquisition.ino 输出，115200 baud，10 Hz）
--------------------------------------------------------------
数据行：  t_ms, V1_mV, V2_mV, P, x_mm, I_nA, U_nV, f_Hz
标定点：  "目标I=... uA, 实测I=... uA, P=..."
标定结果："CAL: k=... A/unitP, b=... A（已存入 EEPROM）"

演示/示例文件均输出到 --demo-out 目录（默认 ./demo_output）。
"""

import argparse
import json
import re
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------------- 中文绘图字体 ----------------
matplotlib.rcParams["font.sans-serif"] = ["Noto Sans CJK SC"]
matplotlib.rcParams["axes.unicode_minus"] = False

OKABE = {
    "blue": "#0072B2", "orange": "#E69F00", "green": "#009E73",
    "red": "#D55E00", "purple": "#CC79A7", "cyan": "#56B4E9",
    "yellow": "#F0E442", "grey": "#999999",
}

# ---------------- 设计默认参数（与《02 理论模型修正》一致） ----------------
DEFAULT_PARAMS = {
    "N1": 50,          # 接收线圈匝数
    "A1": 1.0e-4,      # 接收线圈面积 m²
    "N2": 100,         # 偏转线圈匝数
    "A2": 4.0e-4,      # 偏转线圈面积 m²
    "Bmag": 0.1,       # 偏转区磁感应强度 T
    "k": 1.0e-6,       # 悬线等效扭转劲度 N·m/rad
    "J": 1.0e-7,       # 偏转组转动惯量 kg·m²
    "D": 1.0,          # 光杠杆臂长 m
    "L": 0.02,         # PSD 有效长度 m (20 mm)
    "R_loop": 100.0,   # 回路总电阻 Ω
    "zeta": 0.3,       # 机械阻尼比
}

DATA_RE = re.compile(
    r"^\s*(-?\d+)\s*,\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*,"
    r"\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*,"
    r"\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*$"
)
CAL_RE = re.compile(
    r"目标I\s*=\s*([-+0-9.eE]+)\s*uA\s*,\s*"
    r"实测I\s*=\s*([-+0-9.eE]+)\s*uA\s*,\s*P\s*=\s*([-+0-9.eE]+)"
)
CALFIT_RE = re.compile(r"CAL:\s*k=([-+0-9.eE]+)\s*A/unitP,\s*b=([-+0-9.eE]+)\s*A")
BOOT_RE = re.compile(r"标定参数\s*k=([-+0-9.eE]+)\s*b=([-+0-9.eE]+)")


def load_params(path=None):
    """载入装置参数；None 用设计默认。"""
    p = dict(DEFAULT_PARAMS)
    if path:
        with open(path, encoding="utf-8") as fh:
            user = json.load(fh)
        unknown = set(user) - set(p)
        if unknown:
            print(f"[注意] 参数文件含未知键: {sorted(unknown)}")
        p.update({k: v for k, v in user.items() if k in p})
    p["S"] = 2.0 * p["D"] * p["N2"] * p["A2"] * p["Bmag"] / p["k"]
    p["K_IP"] = p["L"] / (2.0 * p["S"])
    p["f0"] = np.sqrt(p["k"] / p["J"]) / (2.0 * np.pi)
    p["F_BAND"] = 0.2 * p["f0"]
    return p


# ======================================================================
# 1. 串口日志解析
# ======================================================================
def parse_log(path):
    """解析串口日志，返回 dict：
    rows:    np.ndarray [n,8]  数据行（t_ms, V1_mV, V2_mV, P, x_mm, I_nA, U_nV, f_Hz）
    cal:     list[(I_target_uA, I_meas_uA, P)]
    fw_k, fw_b: 固件 CALFIT 拟合结果（若有）
    boot_k, boot_b: 启动打印的 EEPROM 参数（若有）
    """
    rows, cal = [], []
    fw_k = fw_b = boot_k = boot_b = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            m = DATA_RE.match(line)
            if m:
                rows.append([float(g) for g in m.groups()])
                continue
            m = CAL_RE.search(line)
            if m:
                cal.append((float(m.group(1)), float(m.group(2)), float(m.group(3))))
                continue
            m = CALFIT_RE.search(line)
            if m:
                fw_k, fw_b = float(m.group(1)), float(m.group(2))
                continue
            m = BOOT_RE.search(line)
            if m:
                boot_k, boot_b = float(m.group(1)), float(m.group(2))
    data = np.asarray(rows, dtype=float)
    print(f"解析完成：数据行 {len(data)}，标定点 {len(cal)}")
    if fw_k is not None:
        print(f"固件拟合 k={fw_k:.6g} A/unitP, b={fw_b:.6g} A")
    if boot_k is not None:
        print(f"启动 EEPROM 参数 k={boot_k:.6g} A/unitP, b={boot_b:.6g} A")
    return {"rows": data, "cal": cal, "fw_k": fw_k, "fw_b": fw_b,
            "boot_k": boot_k, "boot_b": boot_b}


# ======================================================================
# 2. 后级标定：I = k·P + b
# ======================================================================
def fit_calibration(cal, params):
    """cal: [(I_target, I_meas, P)]，单位 uA。返回拟合统计 dict。"""
    I = np.array([c[1] for c in cal]) * 1e-6          # A（用实测电流）
    P = np.array([c[2] for c in cal])
    A = np.vstack([P, np.ones_like(P)]).T
    (k_fit, b_fit), *_ = np.linalg.lstsq(A, I, rcond=None)
    I_fit = k_fit * P + b_fit
    resid = (I_fit - I) * 1e9                          # nA
    ss_res = np.sum((I_fit - I)**2)
    ss_tot = np.sum((I - I.mean())**2)
    r2 = 1.0 - ss_res / ss_tot
    linearity = np.max(np.abs(I_fit - I)) / np.max(np.abs(I)) * 100
    sigma_fit = np.sqrt(ss_res / max(len(I) - 2, 1)) * 1e9   # 拟合残差标准差 nA
    return {
        "k_fit": k_fit, "b_fit": b_fit, "r2": r2,
        "linearity": linearity, "resid": resid, "sigma_fit": sigma_fit,
        "I_set_uA": np.array([c[0] for c in cal]),
        "I_uA": I * 1e6, "P": P, "K_IP": params["K_IP"],
    }


def print_calibration(res):
    print("\n" + "=" * 60)
    print("后级标定（I = k·P + b）")
    print("=" * 60)
    print(f"  拟合斜率 k = {res['k_fit']:.6e} A/unitP  (设计 K_IP={res['K_IP']:.6e})")
    print(f"  偏差     = {(res['k_fit']/res['K_IP']-1)*100:+.2f}%")
    print(f"  拟合截距 b = {res['b_fit']:.6e} A")
    print(f"  R²       = {res['r2']:.6f}")
    print(f"  线性度   = {res['linearity']:.3f}%  (满量程相对最大偏差，验收 <1%)")
    print(f"  残差标准差 = {res['sigma_fit']:.2f} nA")
    print("\n  设定I(µA)  实测I(µA)  P       残差(nA)")
    for k in range(len(res["I_uA"])):
        print(f"  {res['I_set_uA'][k]:8.3f}  {res['I_uA'][k]:8.3f}  {res['P'][k]:8.4f}  {res['resid'][k]:8.2f}")


# ======================================================================
# 3. 测量段分割（按时间间隔）与段内频率/幅值估计
# ======================================================================
def split_segments(data, gap_factor=3.0):
    """按采样间隔的中位数的 gap_factor 倍把数据切成若干段。"""
    if len(data) < 2:
        return [data]
    t = data[:, 0]
    dt = np.diff(t)
    dt_med = np.median(dt[dt > 0]) if np.any(dt > 0) else 1.0
    breaks = np.where(dt > gap_factor * dt_med)[0]
    idx = np.split(np.arange(len(data)), breaks + 1)
    return [data[i] for i in idx if len(i) >= 5]


def estimate_freq_amp(P, fs, fmin=0.01, fmax=5.0):
    """FFT 估计段内主频与幅值（去直流后），返回 (f_Hz, amp, spec, freqs)。"""
    P = P - P.mean()
    n = len(P)
    spec = np.abs(np.fft.rfft(P)) / n * 2
    freqs = np.fft.rfftfreq(n, 1.0 / fs)
    m = (freqs >= fmin) & (freqs <= fmax)
    if not np.any(m):
        return 0.0, 0.0, spec, freqs
    f_est = freqs[m][np.argmax(spec[m])]
    amp = spec[m][np.argmax(spec[m])]
    return f_est, amp, spec, freqs


# ======================================================================
# 4. 噪声底 / 平均时间优化（Allan 式分块平均）
# ======================================================================
def block_average_curve(P, fs, max_blocks=64):
    """对 P 序列做分块平均：块长 1,2,4,...,max_blocks，返回 (block_len_s, sigma)。"""
    P = P - P.mean()
    sizes = [1]
    while sizes[-1] * 2 <= max_blocks:
        sizes.append(sizes[-1] * 2)
    lens, sigmas = [], []
    for m in sizes:
        n_full = (len(P) // m) * m
        if n_full // m < 2:
            continue
        blocks = P[:n_full].reshape(-1, m)
        means = blocks.mean(axis=1)
        sigmas.append(means.std(ddof=1))
        lens.append(m / fs)
    return np.array(lens), np.array(sigmas)


def noise_analysis(P, k_fit, fs):
    """噪声窗口内：σ_P → σ_I；分块平均曲线；最优平均时间；探测极限。"""
    lens, sig = block_average_curve(P, fs)
    sigma_P_single = P.std(ddof=1)
    sigma_I_single = k_fit * sigma_P_single              # A
    if len(sig) > 1 and np.all(sig > 0):
        i_opt = int(np.argmin(sig))
        t_opt, sigma_P_opt = lens[i_opt], sig[i_opt]
    else:
        t_opt, sigma_P_opt = lens[0], sig[0]
    sigma_I_opt = k_fit * sigma_P_opt
    return {
        "sigma_P_single": sigma_P_single, "sigma_I_single": sigma_I_single,
        "t_opt": t_opt, "sigma_I_opt": sigma_I_opt,
        "lens": lens, "sigmas": sig,
        "dl_3s": 3.0 * k_fit * sigma_P_single,           # 单次 3σ 探测极限
    }


# ======================================================================
# 5. 频率响应（理论 + 实测点）
# ======================================================================
def theoretical_response(params, f=None):
    if f is None:
        f = np.logspace(-2, 1.2, 400)
    r = f / params["f0"]
    H = 1.0 / np.sqrt((1 - r**2)**2 + (2 * params["zeta"] * r)**2)
    return f, H


def freq_response_points(segs, fs, k_fit, freq_list):
    """按 FFT 频率把每个驱动频率匹配到最接近的测量段，返回 (f, |H|) 实测点。
    用频率而非序号匹配，可自动跳过空闲/噪声段。"""
    pts, used = [], set()
    for fset in freq_list:
        best = None
        for i, s in enumerate(segs):
            if i in used:
                continue
            f_est, amp_P, *_ = estimate_freq_amp(s[:, 3], fs)
            if f_est <= 0 or amp_P <= 0:
                continue
            d = abs(f_est - fset)
            if best is None or d < best[0]:
                best = (d, i, f_est, amp_P)
        if best is None:
            continue
        used.add(best[1])
        pts.append((fset, best[2], k_fit * best[3]))
    if not pts:
        return [], []
    I_ref = pts[0][2]
    return [p[0] for p in pts], [p[2] / I_ref for p in pts]


# ======================================================================
# 6. GUM 不确定度预算
# ======================================================================
def gum_uncertainty(params, u_a=None):
    """测量模型 I = L·k/(4·D·N2·A2·Bmag)·P。返回 (名称, 分布, u_rel)。"""
    if u_a is None:
        u_a = 0.005                                # 默认 A 类 0.5%
    comps = [
        ("PSD 位置分辨率 (±0.3 µm, 矩形)", "矩形", params.get("X_PSD", 1e-6) / (params["L"] / 2)),
        ("ADC 量化 (16bit, 矩形)", "矩形", params.get("X_ADC", 1.25e-6) / (params["L"] / 2)),
        ("光杠杆臂长 D (±1%, 矩形)", "矩形", 0.01),
        ("扭转刚度 k 标定 (±2%, 正态)", "正态", 0.02),
        ("磁感应强度 Bmag 不均匀 (±2%, 矩形)", "矩形", 0.02),
        ("偏转线圈面积 A2 (±1%, 矩形)", "矩形", 0.01),
        ("偏转线圈匝数 N2 (±0.5%, 矩形)", "矩形", 0.005),
        ("PSD 有效长度 L (±1%, 矩形)", "矩形", 0.01),
        ("温度漂移/机械零点 (±1%, 矩形)", "矩形", 0.01),
        ("A 类重复性（实测）", "正态", u_a),
    ]
    u = [v / np.sqrt(3) if d == "矩形" else v for _, d, v in comps]
    u_c = np.sqrt(np.sum(np.array(u)**2))
    U = 2 * u_c
    return comps, u, u_c, U


def print_uncertainty(comps, u, u_c, U):
    print("\n" + "=" * 60)
    print("GUM 不确定度预算（相对，满量程 1 µA 计）")
    print("=" * 60)
    for (name, dist, val), uv in zip(comps, u):
        print(f"  {name:<32} u={uv*100:6.3f}%")
    print(f"  {'合成标准不确定度 u_c':<32} {u_c*100:6.3f}%")
    print(f"  {'扩展不确定度 U (k=2)':<32} {U*100:6.3f}%  ->  ±{U*1e6:.1f} nA @ 1 µA")


# ======================================================================
# 7. 绘图
# ======================================================================
def _style(ax):
    for a in ax:
        a.spines["top"].set_visible(False)
        a.spines["right"].set_visible(False)


def fig_calibration(res, outdir):
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(9.5, 3.6))
    I_pts = res["I_uA"]
    # 拟合 I=kP+b 在 (I, P) 平面上的直线：P = (I-b)/k
    I_line = np.linspace(I_pts.min(), I_pts.max(), 100)
    P_line = (I_line * 1e-6 - res["b_fit"]) / res["k_fit"]
    ax.plot(I_pts, res["P"], "o", ms=4, color=OKABE["blue"], label="标定点")
    ax.plot(I_line, P_line, color=OKABE["red"], lw=1.4, label="拟合 $I=kP+b$")
    ax.set_xlabel("注入电流 $I$ (µA)"); ax.set_ylabel("归一化算子 $P$")
    ax.set_title("后级标定：电流 → P")
    ax.legend(frameon=False, fontsize=9); ax.grid(alpha=0.25, lw=0.5)
    ax2.axhline(0, color="black", lw=0.8)
    ax2.plot(res["I_uA"], res["resid"], "s", ms=4, color=OKABE["green"])
    ax2.set_xlabel("注入电流 $I$ (µA)"); ax2.set_ylabel("残差 (nA)")
    ax2.set_title("拟合残差")
    ax2.grid(alpha=0.25, lw=0.5)
    _style((ax, ax2))
    fig.tight_layout()
    p = outdir / "fig_标定与残差.png"
    fig.savefig(p, dpi=300)
    plt.close(fig)
    return p


def fig_time_series(data, outdir):
    fig, ax = plt.subplots(figsize=(7.6, 3.0))
    t = (data[:, 0] - data[0, 0]) / 1000.0
    ax.plot(t, data[:, 3] * 1e3, color=OKABE["blue"], lw=0.8)
    ax.set_xlabel("时间 (s)"); ax.set_ylabel("归一化算子 $P$ (‰)")
    ax.set_title("原始采集：归一化位置算子")
    ax.grid(alpha=0.25, lw=0.5)
    _style((ax,))
    fig.tight_layout()
    p = outdir / "fig_P时间序列.png"
    fig.savefig(p, dpi=300)
    plt.close(fig)
    return p


def fig_noise_curve(na, outdir):
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    sig_p = na["sigmas"] * 1e3                     # ‰
    ax.loglog(na["lens"], sig_p, color=OKABE["blue"], lw=1.5, marker="o", ms=3,
              label="分块平均 σ(P) (‰)")
    i_opt = int(np.argmin(na["sigmas"]))
    ax.axvline(na["t_opt"], color=OKABE["red"], ls=":", lw=1)
    ax.annotate(f"最优平均 {na['t_opt']:.0f} s\n→ σ_I ≈ {na['sigma_I_opt']*1e12:.1f} pA",
                xy=(na["t_opt"], sig_p[i_opt]),
                xytext=(na["t_opt"] * 0.5, sig_p.max() * 2.5),
                fontsize=9, arrowprops=dict(arrowstyle="->", lw=0.8))
    ax.set_xlabel("平均时间 (s)"); ax.set_ylabel("σ(P) (‰)")
    ax.set_title("噪声 vs 平均时间（Allan 式分块平均）")
    ax.grid(alpha=0.25, lw=0.5, which="both")
    _style((ax,))
    fig.tight_layout()
    p = outdir / "fig_噪声与最优平均.png"
    fig.savefig(p, dpi=300)
    plt.close(fig)
    return p


def fig_fft(spec, freqs, f_est, outdir):
    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    m = freqs <= 2.0
    ax.semilogy(freqs[m], spec[m], color=OKABE["blue"], lw=1.0)
    if f_est > 0:
        ax.axvline(f_est, color=OKABE["red"], ls="--", lw=1, label=f"主峰 {f_est:.3f} Hz")
    ax.set_xlabel("频率 (Hz)"); ax.set_ylabel("幅度")
    ax.set_title("测量段频谱（FFT）")
    ax.legend(frameon=False, fontsize=9); ax.grid(alpha=0.25, lw=0.5, which="both")
    _style((ax,))
    fig.tight_layout()
    p = outdir / "fig_频谱.png"
    fig.savefig(p, dpi=300)
    plt.close(fig)
    return p


def fig_uncertainty(comps, u, u_c, U, outdir):
    # 绘图用短标签（报告里保留全名）
    short = {
        "PSD 位置分辨率 (±0.3 µm, 矩形)": "PSD 分辨率",
        "ADC 量化 (16bit, 矩形)": "ADC 量化",
        "光杠杆臂长 D (±1%, 矩形)": "臂长 D",
        "扭转刚度 k 标定 (±2%, 正态)": "扭转刚度 k",
        "磁感应强度 Bmag 不均匀 (±2%, 矩形)": "磁场 Bmag",
        "偏转线圈面积 A2 (±1%, 矩形)": "面积 A2",
        "偏转线圈匝数 N2 (±0.5%, 矩形)": "匝数 N2",
        "PSD 有效长度 L (±1%, 矩形)": "长度 L",
        "温度漂移/机械零点 (±1%, 矩形)": "温度漂移",
        "A 类重复性（实测）": "A 类重复性",
    }
    names = [short.get(c[0], c[0]) for c in comps]
    y = np.arange(len(names))[::-1]
    fig, ax = plt.subplots(figsize=(6.6, 4.6))
    ax.barh(y, np.array(u) * 100, color=OKABE["blue"], alpha=0.85)
    ax.barh(-1, u_c * 100, color=OKABE["red"], alpha=0.9, label=f"合成 $u_c$={u_c*100:.2f}%")
    ax.barh(-2, U * 100, color=OKABE["orange"], alpha=0.9, label=f"扩展 $U$={U*100:.2f}% (k=2)")
    ax.set_yticks(list(y) + [-1, -2])
    ax.set_yticklabels(names + ["合成标准不确定度", "扩展不确定度 (k=2)"], fontsize=9)
    ax.set_xlabel("相对标准不确定度 (%)")
    ax.set_title("GUM 不确定度预算（相对）")
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    ax.grid(alpha=0.25, lw=0.5, axis="x")
    ax.set_ylim(-2.6, len(names) - 0.4)
    _style((ax,))
    fig.tight_layout()
    p = outdir / "fig_不确定度预算.png"
    fig.savefig(p, dpi=300)
    plt.close(fig)
    return p


def fig_freq_response(f, H, f_pts, H_pts, params, outdir):
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    ax.axvspan(0.01, params["F_BAND"], color=OKABE["cyan"], alpha=0.15, label="工作频带 ≤0.2·$f_0$")
    ax.axvline(params["f0"], color=OKABE["grey"], ls="--", lw=1, label=f"$f_0$={params['f0']:.2f} Hz")
    ax.semilogx(f, H, color=OKABE["blue"], lw=1.5, label="理论二阶模型")
    if len(f_pts):
        ax.semilogx(f_pts, H_pts, "o", ms=5, color=OKABE["red"], label="实测点")
    ax.set_xlabel("频率 (Hz)"); ax.set_ylabel("幅值响应 $|H|$")
    ymax = max(2.0, max(H_pts) * 1.15) if len(H_pts) else 2.0
    ax.set_ylim(0, ymax)
    ax.set_title("机械频率响应（验证 C1 修复效果）")
    ax.legend(frameon=False, fontsize=9); ax.grid(alpha=0.25, lw=0.5, which="both")
    _style((ax,))
    fig.tight_layout()
    p = outdir / "fig_频率响应.png"
    fig.savefig(p, dpi=300)
    plt.close(fig)
    return p


# ======================================================================
# 8. 全流程分析
# ======================================================================
def run_analysis(log, params, plot_dir=None, freq_list=None, truth_file=None, fs=10.0):
    d = parse_log(log)
    outdir = Path(plot_dir) if plot_dir else None
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)

    rows = d["rows"]
    if len(rows) == 0:
        print("日志中没有数据行，仅解析了标定信息。")
        return d, None

    # ---- 标定 ----
    cal_res = None
    if d["cal"]:
        cal_res = fit_calibration(d["cal"], params)
        print_calibration(cal_res)
        k_use, b_use = cal_res["k_fit"], cal_res["b_fit"]
    elif d["fw_k"] is not None:
        k_use, b_use = d["fw_k"], d["fw_b"]
        print(f"[使用固件拟合参数] k={k_use:.6g}, b={b_use:.6g}")
    else:
        k_use, b_use = params["K_IP"], 0.0
        print(f"[无标定数据，使用设计参数] K_IP={k_use:.6g} A/unitP")

    # ---- 测量段 ----
    segs = split_segments(rows)
    print(f"测量段数：{len(segs)}（段长 {[len(s) for s in segs]}）")

    # 每段频率/幅值
    seg_stats = []
    for i, s in enumerate(segs):
        f_est, amp, spec, freqs = estimate_freq_amp(s[:, 3], fs)
        I_amp = k_use * amp
        seg_stats.append({"i": i, "f": f_est, "amp_P": amp, "I_amp": I_amp,
                          "sigma_P": s[:, 3].std(ddof=1),
                          "spec": spec, "freqs": freqs, "len": len(s)})
        print(f"  段{i}: 时长{len(s)/fs:.0f}s, f≈{f_est:.3f}Hz, P幅值≈{amp*1e3:.2f}‰, "
              f"I幅值≈{I_amp*1e9:.2f}nA")

    # ---- 噪声窗口：σ(P) 最小的段（空闲/零输入段）----
    idle = min(seg_stats, key=lambda s: s["sigma_P"])
    P_idle = segs[idle["i"]][:, 3]
    na = noise_analysis(P_idle, k_use, fs)
    print("\n" + "=" * 60)
    print(f"噪声底与探测极限（取段{idle['i']}为噪声窗口，时长{len(P_idle)/fs:.0f}s）")
    print("=" * 60)
    print(f"  单次 σ(P) = {na['sigma_P_single']*1e3:.3f} ‰  →  σ(I) = {na['sigma_I_single']*1e12:.2f} pA")
    print(f"  单次 3σ 探测极限 ≈ {na['dl_3s']*1e12:.2f} pA")
    print(f"  最优平均时间 {na['t_opt']:.0f} s → σ(I) ≈ {na['sigma_I_opt']*1e12:.2f} pA")

    # ---- 频率响应 ----
    f_pts, H_pts = [], []
    if freq_list:
        f_pts, H_pts = freq_response_points(segs, fs, k_use, freq_list)
        print("\n频率响应实测点（归一化到首段）:")
        for ff, hh in zip(f_pts, H_pts):
            print(f"  f={ff:5.2f} Hz  |H|={hh:.3f}")
    f_th, H_th = theoretical_response(params)

    # ---- 盲测（--truth：段序号或时间标签 -> 真实电流 µA）----
    truth_dev = None
    if truth_file:
        with open(truth_file, encoding="utf-8") as fh:
            truth = [line.split(",") for line in fh if line.strip() and not line.startswith("#")]
        print("\n" + "=" * 60)
        print("盲测校验（测量电流 vs 真实电流）")
        print("=" * 60)
        truth_dev = []
        for (seg_idx, i_true_uA) in truth:
            idx = int(seg_idx)
            I_m = seg_stats[idx]["I_amp"] * 1e9
            I_t = float(i_true_uA) * 1e3
            if I_t == 0:
                print(f"  段{idx}: 空闲段（真实电流 0），测得 {I_m:.2f}nA —— 不作为盲测点")
                continue
            dev = (I_m - I_t) / I_t * 100
            truth_dev.append((idx, I_t, I_m, dev))
            print(f"  段{idx}: I_true={I_t:7.2f}nA  I_meas={I_m:7.2f}nA  偏差={dev:+6.2f}%")

    # ---- 不确定度 ----
    u_a = (cal_res["sigma_fit"] / 1000.0) if cal_res else 0.005
    comps, u, u_c, U = gum_uncertainty(params, u_a)
    print_uncertainty(comps, u, u_c, U)

    # ---- 绘图 ----
    made = {}
    if outdir:
        if cal_res:
            made["cal"] = fig_calibration(cal_res, outdir)
        made["time"] = fig_time_series(rows, outdir)
        made["noise"] = fig_noise_curve(na, outdir)
        made["fft"] = fig_fft(idle["spec"], idle["freqs"], idle["f"], outdir)
        made["unc"] = fig_uncertainty(comps, u, u_c, U, outdir)
        if freq_list:
            made["fresp"] = fig_freq_response(f_th, H_th, f_pts, H_pts, params, outdir)
        print("\n输出图件：")
        for k, v in made.items():
            print(f"  {k}: {v}")

    # ---- 报告 ----
    report = build_report(d, cal_res, seg_stats, na, f_pts, H_pts, truth_dev,
                          params, u_c, U, k_use)
    return d, {"cal": cal_res, "segments": seg_stats, "noise": na,
               "fresp": (f_pts, H_pts), "unc": (u_c, U), "report": report,
               "figs": made}


def build_report(d, cal, segs, na, f_pts, H_pts, truth_dev, params, u_c, U, k_use):
    L = ["# 实验数据分析报告\n"]
    L.append("## 装置参数（本次分析所用）\n")
    L.append("| 参数 | 值 | 参数 | 值 |")
    L.append("|---|---|---|---|")
    keys = list(params.keys())[:10]
    pairs = [(k, params[k]) for k in ["D", "L", "R_loop", "Bmag", "k", "N2", "A2", "zeta"]]
    L.append("| " + " | ".join(f"{k} = {v:.4g}" for k, v in pairs) + " |")
    L.append("\n## 数据概览")
    L.append(f"- 数据行 {len(d['rows'])}，标定点 {len(d['cal'])}，测量段 {len(segs)}。")
    if cal:
        L.append(f"- 标定斜率 k = {cal['k_fit']:.6e} A/unitP（设计 {cal['K_IP']:.6e}，偏差 "
                 f"{(cal['k_fit']/cal['K_IP']-1)*100:+.2f}%），R² = {cal['r2']:.6f}，"
                 f"线性度 {cal['linearity']:.3f}%。")
    L.append(f"- 噪声窗口单次 σ(I) = {na['sigma_I_single']*1e12:.2f} pA；"
             f"最优平均 {na['t_opt']:.0f} s 后 σ(I) ≈ {na['sigma_I_opt']*1e12:.2f} pA；"
             f"单次 3σ 探测极限 ≈ {na['dl_3s']*1e12:.2f} pA。")
    if len(f_pts):
        pts = "，".join(f"{ff:.2f}Hz:{hh:.2f}" for ff, hh in zip(f_pts, H_pts))
        L.append(f"- 频率响应实测点：{pts}（理论 $f_0$={params['f0']:.2f} Hz，"
                 f"工作频带 ≤ {params['F_BAND']:.2f} Hz）。")
    if truth_dev:
        L.append("- 盲测偏差：")
        for idx, It, Im, dev in truth_dev:
            L.append(f"  - 段{idx}：真实 {It:.1f} nA，测量 {Im:.1f} nA，偏差 {dev:+.2f}%")
    L.append(f"- GUM 合成标准不确定度 u_c = {u_c*100:.2f}%，扩展 U = {U*100:.2f}%（k=2）。")
    L.append("\n> 数据与脚本：analyze_data.py 自动生成。")
    return "\n".join(L)


# ======================================================================
# 9. 示例数据生成（演示模式）
# ======================================================================
def demo_data(params, seed=7):
    """按固件格式生成一份逼真的串口日志与真实电流对照表，返回 (log_text, truth_rows)。"""
    rng = np.random.default_rng(seed)
    fs = 10.0
    S = params["S"]; K = params["K_IP"]
    sigma_P = 2.0 * np.sqrt((1e-6)**2 + (1.25e-6)**2) / params["L"]   # 单次 σ(P)
    lines = []
    t_ms = 0

    def emit_rows(P_series, I_true_nA, f_true, gap_ms=0):
        nonlocal t_ms
        for k, P in enumerate(P_series):
            t_ms += 100
            # 令 (V2-V1)/(V1+V2)=P：取 V1=4(1-P), V2=4(1+P)，和恒为 8
            V1 = 4.0 * (1.0 - P)
            V2 = 4.0 * (1.0 + P)
            I_nA = (K * P) * 1e9
            U_nV = I_nA * params["R_loop"]
            f_out = f_true if (0.005 <= f_true <= 0.10) else 0.0
            lines.append(f"{t_ms}, {V1:.3f}, {V2:.3f}, {P:.5f}, {P*params['L']/2*1e3:.4f}, "
                         f"{I_nA:.2f}, {U_nV:.2f}, {f_out:.5f}")
        t_ms += gap_ms

    # 启动 + 标定
    lines.append("微弱电信号测量系统 固件 v1.0 启动")
    lines.append(f"标定参数 k={K:.6f} b=0.000000")
    lines.append("CAL: 开始扫描（±1 µA 共 9 级）...")
    for Iu in [-1.0, -0.75, -0.5, -0.25, 0.0, 0.25, 0.5, 0.75, 1.0]:
        P = 2.0 * S * Iu * 1e-6 / params["L"] + rng.normal(0, sigma_P / 4)
        I_m = Iu + rng.normal(0, 0.004)
        lines.append(f"  目标I={Iu:.3f} uA, 实测I={I_m:.3f} uA, P={P:.5f}")
    lines.append("CAL: k=%.6f A/unitP, b=0.000000 A（已存入 EEPROM）" % K)

    truth = []
    # 段0：噪声/空闲 60 s
    n0 = int(60 * fs)
    P0 = rng.normal(0, sigma_P, n0)
    emit_rows(P0, 0.0, 0.0, gap_ms=5000)
    truth.append((0, 0.0))
    # 段1-6：频率响应扫描，等幅驱动（段间留 5 s 间隔，模拟实验停顿）
    for i, fdrive in enumerate([0.05, 0.1, 0.2, 0.3, 0.5, 1.0]):
        n = int(20 * fs)
        t = np.arange(n) / fs
        H = theoretical_response(params, np.array([fdrive]))[1][0]
        P_amp = 0.15 * H                        # 等幅驱动，机械响应衰减
        P = P_amp * np.sin(2 * np.pi * fdrive * t) + rng.normal(0, sigma_P, n)
        emit_rows(P, 0.0, fdrive, gap_ms=5000)
        truth.append((i + 1, 0.0))
    # 段7：盲测 0.5 µA 注入，f=0.1 Hz，40 s（准静态近似，不修正 |H(0.1)|）
    n7 = int(40 * fs)
    t7 = np.arange(n7) / fs
    I_true = 0.5e-6
    P_amp7 = 2.0 * S * I_true / params["L"]
    P7 = P_amp7 * np.sin(2 * np.pi * 0.1 * t7) + rng.normal(0, sigma_P, n7)
    emit_rows(P7, I_true * 1e9, 0.1, gap_ms=5000)
    truth.append((7, 0.5))
    # 段8：尾段空闲 30 s
    n8 = int(30 * fs)
    P8 = rng.normal(0, sigma_P, n8)
    emit_rows(P8, 0.0, 0.0, gap_ms=0)
    truth.append((8, 0.0))

    return "\n".join(lines) + "\n", truth


# ======================================================================
# 10. 主入口
# ======================================================================
def main():
    ap = argparse.ArgumentParser(description="实验数据分析工具（微弱电信号测量系统）")
    ap.add_argument("log", nargs="?", help="串口日志文件")
    ap.add_argument("--demo", action="store_true", help="生成示例数据并跑通全流程")
    ap.add_argument("--demo-out", default="demo_output", help="示例数据输出目录")
    ap.add_argument("--plot-dir", default=None, help="图件输出目录（不给出则不绘图）")
    ap.add_argument("--report", default=None, help="Markdown 报告输出路径")
    ap.add_argument("--params", default=None, help="装置参数 JSON（覆盖设计默认）")
    ap.add_argument("--freq-list", default=None, help="频率响应各段驱动频率，如 '0.05,0.1,0.2,0.3,0.5,1.0'")
    ap.add_argument("--truth", default=None, help="盲测真实电流对照 CSV（段号,µA）")
    ap.add_argument("--fs", type=float, default=10.0, help="数据采样率 Hz（默认 10）")
    args = ap.parse_args()

    params = load_params(args.params)
    print(f"装置参数：S={params['S']:.3g} m/A, K_IP={params['K_IP']:.3g} A/unitP, "
          f"f0={params['f0']:.3f} Hz, 频带≤{params['F_BAND']:.3f} Hz")

    freq_list = [float(x) for x in args.freq_list.split(",")] if args.freq_list else None

    if args.demo:
        dout = Path(args.demo_out)
        dout.mkdir(parents=True, exist_ok=True)
        log_text, truth = demo_data(params)
        log_p = dout / "demo_串口日志.txt"
        log_p.write_text(log_text, encoding="utf-8")
        truth_p = dout / "demo_真实电流.csv"
        truth_p.write_text("# 段序号,真实电流_uA\n" +
                           "\n".join(f"{i},{v}" for i, v in truth) + "\n", encoding="utf-8")
        print(f"\n已生成示例日志: {log_p}")
        print(f"已生成真实电流对照: {truth_p}")
        log = str(log_p)
        args.report = args.report or str(dout / "demo_分析报告.md")
        args.plot_dir = args.plot_dir or str(dout / "figs")
        args.truth = args.truth or str(truth_p)
        args.freq_list = args.freq_list or "0.05,0.1,0.2,0.3,0.5,1.0"
        freq_list = [0.05, 0.1, 0.2, 0.3, 0.5, 1.0]
    else:
        if not args.log:
            ap.error("请提供日志文件，或使用 --demo")
        log = args.log

    _, out = run_analysis(log, params, plot_dir=args.plot_dir,
                          freq_list=freq_list, truth_file=args.truth, fs=args.fs)
    if out and args.report:
        Path(args.report).write_text(out["report"], encoding="utf-8")
        print(f"\n报告已写入: {args.report}")


if __name__ == "__main__":
    main()
