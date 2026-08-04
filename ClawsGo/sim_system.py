# -*- coding: utf-8 -*-
"""
《基于 Arduino 嵌入式开发与光杠杆放大的微弱电信号测量》系统级物理仿真
=========================================================================
作者：ClawsGO Science  (供论文推进使用)
日期：2026-08-03

功能：
  1) 后级标定：电流 I -> 归一化算子 P 的线性标定（含噪声、拟合、残差、线性度）
  2) 前级传递：发射场 B0 -> 接收线圈感应电流 I 的理论映射
  3) 全链路盲测：设定场强 -> PSD 输出 -> 经标定反推电流/场强，评估精度
  4) 机械频率响应：二阶振子传递函数与工作频带
  5) 噪声底与探测极限：PSD/ADC 白噪声、Johnson、Brown 热噪声、漂移 vs 平均时间
  6) GUM 不确定度预算：分量 -> 合成 -> 扩展不确定度
  7) 全链路时域仿真：B(t) -> θ(t) -> P(t) -> 反推 I(t)、f，含滑动平均降噪

所有物理量与国际单位制一致；结果写入 results/ 目录，图输出为 PNG (300 dpi)。
默认参数与《02_理论模型修正与量化设计.md》一致，可一键复现。
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

# ----------------------------------------------------------------------
# 中文绘图字体（避免豆腐块）
# ----------------------------------------------------------------------
matplotlib.rcParams["font.sans-serif"] = ["Noto Sans CJK SC"]
matplotlib.rcParams["axes.unicode_minus"] = False

OKABE = {
    "blue": "#0072B2", "orange": "#E69F00", "green": "#009E73",
    "red": "#D55E00", "purple": "#CC79A7", "cyan": "#56B4E9",
    "yellow": "#F0E442", "grey": "#999999",
}

OUT = Path(__file__).resolve().parent / "results"
OUT.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(42)          # 可复现

# ======================================================================
# 1. 系统参数（设计示例）
# ======================================================================
N1 = 50          # 接收线圈匝数
A1 = 1.0e-4      # 接收线圈面积 m^2 (1cm x 1cm)
N2 = 100         # 偏转线圈匝数
A2 = 4.0e-4      # 偏转线圈面积 m^2 (2cm x 2cm)
Bmag = 0.1       # 偏转区磁感应强度 T
k = 1.0e-6       # 悬线等效扭转劲度 N·m/rad
J = 1.0e-7       # 偏转组转动惯量 kg·m^2
D = 1.0          # 光杠杆臂长 m（镜面到 PSD）
L = 0.02         # PSD 有效长度 m (20 mm)
R_loop = 100.0   # 回路总电阻 Ω（接收+导线+偏转+采样）
zeta = 0.3       # 机械阻尼比
T_K = 300.0      # 环境温度 K
kB = 1.380649e-23

FS = 50          # 采样率 Hz（Arduino 滑动窗口实现）
X_PSD = 1.0e-6   # PSD+电子读出位置噪声（单次采样 RMS，m）
X_ADC = 1.25e-6  # ADC 量化等效位置噪声（m，16bit/±4.096V 下估算）
X0_OFF = 0.2e-3  # 光路零点偏移 m（机械/光学安装误差）

# ---- 由参数导出的核心指标 ----
S = 2.0 * D * N2 * A2 * Bmag / k            # 电流灵敏度 m/A
K_IP = L / (2.0 * S)                        # I = K_IP*P 中的系数 A/unitP
f0 = np.sqrt(k / J) / (2.0 * np.pi)         # 机械固有频率 Hz
F_BAND = 0.2 * f0                           # 建议工作频带上限

print("=" * 72)
print("关键设计指标")
print("=" * 72)
print(f"电流灵敏度  S        = {S:.4g} m/A   (1 uA -> {S*1e-6*1e3:.1f} mm)")
print(f"转换系数    K_IP     = {K_IP:.4g} A/unitP")
print(f"固有频率    f0       = {f0:.3f} Hz")
print(f"工作频带上限 f_band  = {F_BAND:.3f} Hz  (幅值误差<5%)")
print(f"满量程电流 (|P|<=0.8)= {0.8*K_IP*1e6:.2f} uA")

# ======================================================================
# 2. 噪声模型
# ======================================================================
X_NOISE_WHITE = np.sqrt(X_PSD**2 + X_ADC**2)   # 单次采样白噪声（PSD+ADC）
# 悬摆 Brown 热噪声谱密度（角噪声，rad^2/Hz），0 频极限
S_THETA_0 = 4 * kB * T_K * zeta / (J * (np.sqrt(k / J))**3)
TAU_C = 1.0 / (zeta * np.sqrt(k / J))          # 机械相关时间 s

def sigma_brown(T_avg):
    """等效输入电流 Brown 噪声 (A)，平均时间 T_avg (s)。
    短平均受 equipartition 上限约束，长平均按 PSD/2T 收敛。"""
    theta_eq = np.sqrt(kB * T_K / k)                 # 均衡角波动 (rad)
    theta_avg = np.sqrt(S_THETA_0 / (2.0 * np.maximum(T_avg, 1e-9)))
    theta = np.minimum(theta_eq, theta_avg)
    return (2 * D / S) * theta

def sigma_white(T_avg):
    """PSD+ADC 白噪声等效电流 (A)，按 sqrt(N) 平均下降。"""
    N = np.maximum(FS * T_avg, 1)
    return (X_NOISE_WHITE / S) / np.sqrt(N)

def sigma_johnson(T_avg):
    """回路电阻 Johnson 噪声等效电流 (A)，带宽 ~1/(2T_avg)。"""
    df = 1.0 / (2.0 * np.maximum(T_avg, 1e-9))
    return np.sqrt(4 * kB * T_K * R_loop * df) / R_loop

DRIFT_RATE = 1.0e-12      # 系统漂移速率（电流等效） A/s，即 1 pA/s

def sigma_drift(T_avg):
    """环境/温度/机械零点漂移（线性积累）。"""
    return DRIFT_RATE * T_avg

# ======================================================================
# 3. 后级标定：电流 I -> 归一化算子 P
# ======================================================================
def p_of_current(I_cal, x0=X0_OFF):
    """理想 PSD 输出：P = 2*(S*I + x0)/L（准静态）。"""
    return 2.0 * (S * I_cal + x0) / L

def calibrate():
    """注入已知电流 -> 采集含噪 P -> 最小二乘拟合 I = k_IP_fit*P + b_IP。"""
    I_cal = np.array([-1.0, -0.75, -0.5, -0.25, 0.0,
                       0.25, 0.5, 0.75, 1.0]) * 1e-6      # 9 级, ±1 uA
    N_AVG = 16                                            # 每点平均次数
    P_true = p_of_current(I_cal)
    P_meas = P_true + rng.normal(0, 2 * X_NOISE_WHITE / L, P_true.size) / np.sqrt(N_AVG)
    sigma_P = np.full_like(P_meas, 2 * X_NOISE_WHITE / L / np.sqrt(N_AVG))

    # 线性拟合 I = k*P + b
    A = np.vstack([P_meas, np.ones_like(P_meas)]).T
    (k_fit, b_fit), res, *_ = np.linalg.lstsq(A, I_cal, rcond=None)
    I_fit = k_fit * P_meas + b_fit
    resid = (I_fit - I_cal) * 1e9                          # nA
    ss_res = np.sum((I_fit - I_cal)**2)
    ss_tot = np.sum((I_cal - I_cal.mean())**2)
    r2 = 1 - ss_res / ss_tot
    linearity = np.max(np.abs(I_fit - I_cal)) / I_cal.max() * 100  # %

    print("\n后级标定结果 (I = k*P + b)")
    print(f"  拟合斜率 k = {k_fit:.4e} A/unitP   (理论 {K_IP:.4e})")
    print(f"  拟合截距 b = {b_fit:.3e} A")
    print(f"  相关系数 R^2 = {r2:.6f}")
    print(f"  线性度 (最大偏差/满量程) = {linearity:.3f}%")
    return I_cal, P_meas, sigma_P, k_fit, b_fit, resid, r2, linearity

# ======================================================================
# 4. 前级映射（场强 B0 -> 感应电流 I，准静态 f<f_band）
# ======================================================================
def current_of_field(B0, f):
    """接收线圈感应电流幅值：I = N1*A1*2*pi*f*B0 / R_loop。"""
    return N1 * A1 * (2 * np.pi * f) * B0 / R_loop

# ======================================================================
# 5. 全链路盲测
# ======================================================================
def blind_test(k_fit, b_fit, f=0.1, T_avg=40.0):
    """设定场强 B0 -> 预测 P -> 加噪 -> 反推电流/场强。"""
    B0_set = np.array([2, 5, 10, 20, 50, 100]) * 1e-6      # uT
    I_true = current_of_field(B0_set, f)
    x_true = S * I_true
    P_true = 2 * (x_true + X0_OFF) / L
    N = int(FS * T_avg)
    P_meas = P_true + rng.normal(0, 2 * X_NOISE_WHITE / L, P_true.size) / np.sqrt(N)
    I_meas = k_fit * P_meas + b_fit
    B0_meas = I_meas * R_loop / (N1 * A1 * 2 * np.pi * f)
    rel = (I_meas - I_true) / I_true * 100
    # 相对不确定度：以 1 uA 满量程、约 4% 相对系统不确定度估计（见第 8 节）
    u_rel = 0.04
    U = 2 * u_rel * np.abs(I_meas)

    print("\n全链路盲测 (f = %.2f Hz, 平均 %.0f s)" % (f, T_avg))
    print(f"  {'B0_set/uT':>10} {'I_true/nA':>10} {'I_meas/nA':>10} {'偏差/%':>8} {'U/nA(k=2)':>10}")
    for i in range(len(B0_set)):
        print(f"  {B0_set[i]*1e6:10.0f} {I_true[i]*1e9:10.3f} {I_meas[i]*1e9:10.3f} "
              f"{rel[i]:8.2f} {U[i]*1e9:10.2f}")
    np.savetxt(OUT / "measurement_table.csv",
               np.column_stack([B0_set*1e6, I_true*1e9, I_meas*1e9, rel, U*1e9]),
               header="B0_set(uT),I_true(nA),I_meas(nA),rel_dev(%),U_nA(k=2)",
               delimiter=",", fmt="%.3f", comments="")
    return B0_set, I_true, I_meas, rel, U

# ======================================================================
# 6. 频率响应
# ======================================================================
def freq_response():
    f = np.logspace(-2, 2, 800)          # 0.01 - 100 Hz
    r = f / f0
    H = 1.0 / np.sqrt((1 - r**2)**2 + (2 * zeta * r)**2)
    phase = -np.degrees(np.arctan2(2 * zeta * r, 1 - r**2))
    return f, H, phase

# ======================================================================
# 7. GUM 不确定度预算
# ======================================================================
def uncertainty_budget(I_ref=1e-6):
    """测量模型 I = L*k/(4*D*N2*A2*Bmag) * P，给出分量表（相对不确定度）。
    返回 (名称, 分布, 相对标准不确定度列表)。"""
    comps = [
        ("PSD 位置分辨率 (0.3 um, 矩形)",        "矩形", X_PSD / (L / 2)),
        ("ADC 量化 (16bit, 矩形)",               "矩形", X_ADC / (L / 2)),
        ("光杠杆臂长 D (±1%, 矩形)",             "矩形", 0.01),
        ("扭转刚度 k 标定 (±2%, 正态)",          "正态", 0.02),
        ("磁感应强度 Bmag 不均匀 (±2%, 矩形)",   "矩形", 0.02),
        ("偏转线圈面积 A2 (±1%, 矩形)",          "矩形", 0.01),
        ("偏转线圈匝数 N2 (±0.5%, 矩形)",        "矩形", 0.005),
        ("PSD 有效长度 L (±1%, 矩形)",           "矩形", 0.01),
        ("温度漂移/机械零点 (±1%, 矩形)",        "矩形", 0.01),
        ("A 类重复性 (标定残差)",                "正态", 0.005),
    ]
    # 各分量标准不确定度（矩形->/sqrt(3)，正态->/1）
    u_rel = []
    for name, dist, val in comps:
        u = val / np.sqrt(3) if dist == "矩形" else val
        u_rel.append(u)
    u_c = np.sqrt(np.sum(np.array(u_rel)**2))           # 合成（相对）
    U = 2 * u_c                                         # 扩展 k=2（相对）
    print("\nGUM 不确定度预算（相对, 以 I_ref = %.2f uA 计）" % (I_ref*1e6))
    print(f"  合成标准不确定度 u_c = {u_c*100:.2f}%")
    print(f"  扩展不确定度 U(k=2)  = {U*100:.2f}%  ->  ±{U*I_ref*1e9:.1f} nA @ {I_ref*1e6:.2f} uA")
    return comps, u_rel, u_c, U

# ======================================================================
# 8. 绘图
# ======================================================================
def fig_calibration(I_cal, P_meas, sigma_P, k_fit, b_fit, resid):
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(9.5, 3.8))
    xp = np.linspace(P_meas.min(), P_meas.max(), 100)
    ax.errorbar(I_cal * 1e6, P_meas, yerr=sigma_P, fmt="o", ms=4, capsize=2,
                color=OKABE["blue"], ecolor=OKABE["grey"], label="标定点（含噪）")
    ax.plot((k_fit * xp + b_fit) * 1e6 / 1e-6, xp, color=OKABE["red"], lw=1.5,
            label="拟合 $I=kP+b$")
    ax.set_xlabel("注入电流 $I$ (µA)"); ax.set_ylabel("归一化算子 $P$")
    ax.set_title("后级标定：电流 → 归一化位置算子")
    ax.legend(frameon=False, fontsize=9); ax.grid(alpha=0.25, lw=0.5)

    ax2.axhline(0, color="black", lw=0.8)
    ax2.plot(I_cal * 1e6, resid, "s", ms=4, color=OKABE["green"])
    ax2.set_xlabel("注入电流 $I$ (µA)"); ax2.set_ylabel("残差 (nA)")
    ax2.set_title("拟合残差")
    ax2.grid(alpha=0.25, lw=0.5)
    for a in (ax, ax2):
        a.spines["top"].set_visible(False); a.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT.parent / "fig1_校准曲线与残差.png", dpi=300)
    plt.close(fig)

def fig_freq_response():
    f, H, phase = freq_response()
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(6.4, 5.4), sharex=True)
    ax.axvspan(0.01, F_BAND, color=OKABE["cyan"], alpha=0.15, label="工作频带 $f\\leq 0.2f_0$")
    ax.axvline(f0, color=OKABE["grey"], ls="--", lw=1, label=f"$f_0$={f0:.2f} Hz")
    ax.semilogx(f, H, color=OKABE["blue"], lw=1.6)
    ax.set_ylabel("幅值响应 $|H|$"); ax.legend(frameon=False, fontsize=9)
    ax.set_ylim(0, 2); ax.grid(alpha=0.25, lw=0.5, which="both")

    ax2.axvspan(0.01, F_BAND, color=OKABE["cyan"], alpha=0.15)
    ax2.axvline(f0, color=OKABE["grey"], ls="--", lw=1)
    ax2.semilogx(f, phase, color=OKABE["orange"], lw=1.6)
    ax2.set_xlabel("频率 $f$ (Hz)"); ax2.set_ylabel("相位 (°)")
    ax2.set_ylim(-200, 0); ax2.grid(alpha=0.25, lw=0.5, which="both")
    for a in (ax, ax2):
        a.spines["top"].set_visible(False); a.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT.parent / "fig2_机械频率响应.png", dpi=300)
    plt.close(fig)

def fig_noise():
    T = np.logspace(-1.6, 2.4, 300)                       # 0.025 - 250 s
    iw = sigma_white(T) * 1e12
    ij = sigma_johnson(T) * 1e12
    ib = sigma_brown(T) * 1e12
    idr = sigma_drift(T) * 1e12
    ic = np.sqrt(iw**2 + ij**2 + ib**2 + idr**2) * 1e-12

    fig, ax = plt.subplots(figsize=(6.6, 4.2))
    ax.loglog(T, iw, color=OKABE["blue"], label="PSD+ADC 白噪声")
    ax.loglog(T, ij, color=OKABE["green"], label="回路电阻 Johnson 噪声")
    ax.loglog(T, ib, color=OKABE["purple"], label="悬摆 Brown 热噪声")
    ax.loglog(T, idr, color=OKABE["red"], ls="--", label="系统漂移 (1 pA/s)")
    ax.loglog(T, ic * 1e12, color="black", lw=1.8, label="合成噪声")
    t_opt = T[np.argmin(ic)]
    ax.axvline(t_opt, color="black", ls=":", lw=1)
    ax.annotate(f"最优平均时间 ≈{t_opt:.0f} s\n(合成噪声≈{ic.min()*1e12:.1f} pA)",
                xy=(t_opt, ic.min() * 1e12), xytext=(t_opt * 0.9, ic.min() * 1e12 * 6),
                fontsize=9, arrowprops=dict(arrowstyle="->", lw=0.8))
    ax.set_xlabel("平均时间 $T$ (s)"); ax.set_ylabel("等效输入电流噪声 (pA)")
    ax.set_title("噪声底与探测极限 vs 平均时间")
    ax.legend(frameon=False, fontsize=9); ax.grid(alpha=0.25, lw=0.5, which="both")
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT.parent / "fig3_噪声与探测极限.png", dpi=300)
    plt.close(fig)
    print(f"\n最优平均时间 ≈ {t_opt:.1f} s，合成噪声 ≈ {ic.min()*1e12:.2f} pA")

def fig_chain(k_fit, b_fit, f=0.1, B0=20e-6, T_total=40.0):
    """全链路时域仿真：B0=20 uT, f=0.1 Hz。"""
    n = int(FS * T_total)
    t = np.arange(n) / FS
    B = B0 * np.sin(2 * np.pi * f * t)
    I_true = current_of_field(B, f)
    x = S * I_true
    P_true = 2 * (x + X0_OFF) / L
    P_meas = P_true + rng.normal(0, 2 * X_NOISE_WHITE / L, n)
    # 滑动平均（窗口 25 点 = 0.5 s）
    win = np.ones(25) / 25
    P_filt = np.convolve(P_meas, win, mode="same")
    I_meas = k_fit * P_filt + b_fit

    # 频率估计（FFT 主峰）+ 幅值最小二乘
    seg = slice(int(0.5 * n), None)
    spec = np.abs(np.fft.rfft(P_filt[seg] - P_filt[seg].mean()))
    freqs = np.fft.rfftfreq(len(P_filt[seg]), 1 / FS)
    f_est = freqs[np.argmax(spec)]
    t2 = t[seg]
    A = np.vstack([np.sin(2*np.pi*f_est*t2), np.cos(2*np.pi*f_est*t2),
                   np.ones_like(t2)]).T
    coef, *_ = np.linalg.lstsq(A, P_filt[seg], rcond=None)
    P_amp_est = np.hypot(coef[0], coef[1])
    I_amp_est = k_fit * P_amp_est
    B_amp_est = I_amp_est * R_loop / (N1 * A1 * 2 * np.pi * f_est)

    print("\n全链路时域仿真 (B0=%.0f uT, f=%.2f Hz)" % (B0*1e6, f))
    print(f"  估计频率 f = {f_est:.3f} Hz  (设定 {f} Hz)")
    print(f"  估计电流幅值 = {I_amp_est*1e9:.2f} nA (设定 {np.abs(I_true).max()*1e9:.2f} nA)")
    print(f"  估计场强幅值 = {B_amp_est*1e6:.2f} uT (设定 {B0*1e6:.0f} uT)")

    fig, axs = plt.subplots(4, 1, figsize=(7.2, 7.6), sharex=True)
    axs[0].plot(t, B * 1e6, color=OKABE["blue"], lw=1)
    axs[0].set_ylabel("输入场 $B$ (µT)")
    axs[1].plot(t, x * 1e6, color=OKABE["green"], lw=1)
    axs[1].set_ylabel("光斑位移 $x$ (µm)")
    axs[2].plot(t, P_meas * 1e3, color=OKABE["grey"], lw=0.6, alpha=0.6, label="原始")
    axs[2].plot(t, P_filt * 1e3, color=OKABE["red"], lw=1.2, label="滑动平均后")
    axs[2].set_ylabel("归一化算子 $P$ (‰)")
    axs[2].legend(frameon=False, fontsize=9, loc="upper right")
    axs[3].plot(t, I_true * 1e9, color=OKABE["blue"], lw=1.4, label="真实电流")
    axs[3].plot(t, I_meas * 1e9, color=OKABE["orange"], lw=1.2, ls="--", label="测量电流")
    axs[3].set_ylabel("电流 $I$ (nA)"); axs[3].set_xlabel("时间 $t$ (s)")
    axs[3].legend(frameon=False, fontsize=9, loc="upper right")
    for a in axs:
        a.grid(alpha=0.25, lw=0.5)
        a.spines["top"].set_visible(False); a.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT.parent / "fig4_全链路时域仿真.png", dpi=300)
    plt.close(fig)

def fig_uncertainty(comps, u_rel, u_c, U):
    names = [c[0] for c in comps]
    fig, ax = plt.subplots(figsize=(6.8, 4.6))
    y = np.arange(len(names))[::-1]
    bars = ax.barh(y, np.array(u_rel) * 100, color=OKABE["blue"], alpha=0.85)
    ax.barh(-1, u_c * 100, color=OKABE["red"], alpha=0.9, label=f"合成 $u_c$={u_c*100:.2f}%")
    ax.barh(-2, U * 100, color=OKABE["orange"], alpha=0.9, label=f"扩展 $U$={U*100:.2f}% (k=2)")
    ax.set_yticks(list(y) + [-1, -2])
    ax.set_yticklabels(names + ["合成标准不确定度", "扩展不确定度 (k=2)"], fontsize=8.5)
    ax.set_xlabel("相对标准不确定度 (%)")
    ax.set_title("GUM 不确定度预算（相对）")
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    ax.grid(alpha=0.25, lw=0.5, axis="x")
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT.parent / "fig5_不确定度预算.png", dpi=300)
    plt.close(fig)

# ======================================================================
# 9. 主流程
# ======================================================================
if __name__ == "__main__":
    # 后级标定
    I_cal, P_meas, sigma_P, k_fit, b_fit, resid, r2, lin = calibrate()

    # 标定数据表
    np.savetxt(OUT / "calibration_table.csv",
               np.column_stack([I_cal*1e6, P_meas, sigma_P, resid]),
               header="I_cal(uA),P_meas,P_sigma,resid(nA)", delimiter=",",
               fmt="%.6f", comments="")

    # 盲测
    B0_set, I_true, I_meas, rel, U = blind_test(k_fit, b_fit)

    # 频率响应 + 噪声 + 不确定度
    f, H, phase = freq_response()
    comps, u_rel_list, u_c, U_exp = uncertainty_budget()

    # 不确定度表
    with open(OUT / "uncertainty_budget.csv", "w") as fh:
        fh.write("component,distribution,value,u_rel(%)\n")
        for (name, dist, val), u in zip(comps, u_rel_list):
            fh.write(f"{name},{dist},{val:.4g},{u*100:.3f}\n")
        fh.write(f"combined,,,{u_c*100:.2f}\n")
        fh.write(f"expanded_k2,,,{U_exp*100:.2f}\n")

    # 时域仿真
    fig_chain(k_fit, b_fit)

    # 绘图
    fig_calibration(I_cal, P_meas, sigma_P, k_fit, b_fit, resid)
    fig_freq_response()
    fig_noise()
    fig_uncertainty(comps, u_rel_list, u_c, U_exp)

    # 汇总文档
    # 最优平均时间（用于汇总）
    T_grid = np.exp(np.linspace(-1.6, 2.4, 300))
    i_comb_grid = np.sqrt(sigma_white(T_grid)**2 + sigma_johnson(T_grid)**2
                          + sigma_brown(T_grid)**2 + sigma_drift(T_grid)**2)
    t_opt = float(T_grid[np.argmin(i_comb_grid)])

    summary = f"""# 仿真结果汇总（sim_system.py 一键生成）

## 设计指标
- 电流灵敏度 S = {S:.3g} m/A（1 µA → {S*1e-6*1e3:.1f} mm）
- 转换系数 K_IP = {K_IP:.3g} A/单位P
- 固有频率 f0 = {f0:.3f} Hz；工作频带上限 f_band = {F_BAND:.3f} Hz
- 满量程电流（|P|≤0.8）= {0.8*K_IP*1e6:.2f} µA

## 后级标定
- 拟合斜率 k = {k_fit:.3e} A/单位P，截距 b = {b_fit:.3e} A
- R² = {r2:.6f}，线性度 = {lin:.3f}%（满量程相对最大偏差）

## 盲测（f=0.1 Hz，平均 40 s）
- 平均后位置噪声 ≈ {2*X_NOISE_WHITE/L/np.sqrt(FS*40)*L/2*1e6:.2f} µm
- 对应电流检测极限 ≈ {X_NOISE_WHITE/np.sqrt(FS*40)/S*1e12:.1f} pA
- 扩展不确定度（k=2）≈ {U_exp*100:.1f}%（相对，~满量程计）

## 噪声与探测极限
- 最优平均时间 ≈ {t_opt:.0f} s，该处合成噪声 ≈ {i_comb_grid.min()*1e12:.1f} pA
- 单次采样白噪声等效电流 ≈ {X_NOISE_WHITE/S*1e12:.1f} pA
- Brown 热噪声（长平均 40 s）≈ {sigma_brown(40)*1e12:.1f} pA

## GUM 不确定度
- 合成标准不确定度 u_c = {u_c*100:.2f}%（相对）
- 扩展不确定度 U = {U_exp*100:.2f}%（相对, k=2）

> 说明：以上为示例参数下的理论预测，用于支撑论文第 7/8/9 章的量化论述与
> 实验预期值；实测数据应按照《04_实验验证方案》采集后替换。
"""
    (OUT / "summary.md").write_text(summary, encoding="utf-8")
    print("\n输出文件：")
    for p in sorted(OUT.iterdir()):
        print("  ", p)
    for p in sorted(OUT.parent.glob("fig*.png")):
        print("  ", p)
    print("\n仿真完成。")
