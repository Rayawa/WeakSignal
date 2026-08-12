# 系统级物理仿真（sim_system.py）— 参数化版

《基于 Arduino 嵌入式开发与光杠杆放大的微弱电信号测量》全链路仿真：后级标定、
前级场—电流映射、盲测、机械频率响应、噪声底与探测极限、GUM 不确定度预算、
时域全链路仿真。

## 参数化用法

```bash
# 1) 设计示例参数（默认组）：输出到 results/ 与脚本目录（与论文图件一致）
python3 sim_system.py

# 2) 用装置实际参数跑（覆盖默认值），输出隔离到 results/<tag>/ 与 figs_<tag>/
python3 sim_system.py --config device_configs/lab_variant.json

# 3) 指定参数组名（覆盖配置文件的 name 字段）
python3 sim_system.py --config device_configs/lab_variant.json --tag lab1

# 4) 查看参数注册表（键、含义、单位、默认值、说明）
python3 sim_system.py --list-params
```

## 配置文件格式（device_configs/*.json）

JSON 中只写需要覆盖的参数键；缺省用设计默认值。`name` 为参数组名（决定输出
目录），`comment` 为备注，二者不参与参数合并。未识别的键会告警并忽略。

```json
{
  "name": "lab_variant",
  "comment": "实验室搭建变体……",
  "N1": 40, "A1": 9.0e-5, "N2": 80, "A2": 3.2e-4,
  "Bmag": 0.08, "k": 1.4e-6, "J": 1.2e-7,
  "D": 0.9, "L": 0.012, "R_loop": 120.0, "zeta": 0.35
}
```

## 参数注册表

| 键 | 含义 | 单位 | 默认值 | 说明 |
|---|---|---|---|---|
| N1 | 接收线圈匝数 | 匝 | 50 | 电磁感应接收线圈 |
| A1 | 接收线圈面积 | m² | 1e-4 | 1 cm × 1 cm |
| N2 | 偏转线圈匝数 | 匝 | 100 | 悬吊偏转线圈 |
| A2 | 偏转线圈面积 | m² | 4e-4 | 2 cm × 2 cm |
| Bmag | 偏转区磁感应强度 | T | 0.1 | 钕铁硼永磁体气隙 |
| k | 悬线等效扭转劲度 | N·m/rad | 1e-6 | 双丝悬吊 |
| J | 偏转组转动惯量 | kg·m² | 1e-7 | 线圈+镜体 |
| D | 光杠杆臂长 | m | 1.0 | 镜面至 PSD |
| L | PSD 有效长度 | m | 0.02 | 20 mm |
| R_loop | 回路总电阻 | Ω | 100 | 接收+导线+偏转+采样 |
| zeta | 机械阻尼比 | — | 0.3 | 空气/丝阻尼 |

派生量自动计算：电流灵敏度 S、转换系数 K_IP、固有频率 f0、工作频带上限
f_band=0.2·f0、噪声模型常量。

## 输出

| 文件 | 说明 |
|---|---|
| results/<tag>/calibration_table.csv | 标定点与残差 |
| results/<tag>/measurement_table.csv | 盲测场强/电流/偏差/不确定度 |
| results/<tag>/uncertainty_budget.csv | GUM 分量 + 合成 + 扩展 |
| results/<tag>/summary.md | 汇总报告（参数表 + 全部指标） |
| figs_<tag>/fig1~fig5_*.png | 五张图件 |

## 与实验数据分析工具的联动

`08_实验数据分析/analyze_data.py --params <同上 JSON>` 与仿真共用同一套装置参数
文件（缺省键取设计默认值），保证仿真预测与实测分析口径一致。

## 已交付参数组

- **default**：设计示例（论文第 7/8/9 章所用）：S=8000 m/A，K_IP=1.25 µA/P，
  f0=0.503 Hz，最优平均 7.7 s → 13.43 pA，u_c=2.65%，U=5.29%。
- **lab_variant**：实验室搭建变体（更小更柔、12 mm PSD、磁体 0.08 T、回路 120 Ω）：
  S=2633 m/A，K_IP=2.28 µA/P，f0=0.544 Hz，最优平均 15.7 s → 27.20 pA；
  灵敏度降低导致弱场盲测偏差增大（2 µT→81%，100 µT→2.6%）。
