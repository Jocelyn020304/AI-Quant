"""
任务四：扩展技术指标 KDJ（随机指标）计算与可视化
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import os

# ---------- 配置 ----------
CSV_PATH = r'C:\Users\Administrator\Desktop\量化交易：AI大模型辅助的金融交易策略\Task 1\寒武纪_过去一年日线数据.csv'
OUTPUT_DIR = r'C:\Users\Administrator\Desktop\量化交易：AI大模型辅助的金融交易策略\Task 2'

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

# ---------- 1. 加载数据 ----------
df = pd.read_csv(CSV_PATH, encoding='utf-8-sig')
df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')
df = df.sort_values('trade_date').reset_index(drop=True)
close = df['close'].values
high = df['high'].values
low = df['low'].values
dates = df['trade_date'].values

# ---------- 2. 计算 KDJ (9, 3, 3) ----------
def calc_kdj(high, low, close, n=9, k1=3, d1=3):
    """
    KDJ 随机指标计算
    参数: N=9 (RSV周期), K1=3 (K平滑), D1=3 (D平滑)
    """
    length = len(close)
    rsv = np.full(length, np.nan)
    k = np.full(length, np.nan)
    d = np.full(length, np.nan)
    j = np.full(length, np.nan)

    for i in range(n - 1, length):
        h_n = np.max(high[i - n + 1:i + 1])
        l_n = np.min(low[i - n + 1:i + 1])
        if h_n != l_n:
            rsv[i] = (close[i] - l_n) / (h_n - l_n) * 100
        else:
            rsv[i] = 50  # 当最高最低相等时取中间值

    # K、D 初始值
    k[n - 1] = 50
    d[n - 1] = 50

    for i in range(n, length):
        k[i] = (k1 - 1) / k1 * k[i - 1] + (1 / k1) * rsv[i]
        d[i] = (d1 - 1) / d1 * d[i - 1] + (1 / d1) * k[i]

    j = 3 * d - 2 * k

    return rsv, k, d, j

rsv, k, d, j = calc_kdj(high, low, close, n=9, k1=3, d1=3)

# 最新值
print("===== KDJ 指标计算结果 =====")
print(f"最新 RSV = {rsv[-1]:.2f}")
print(f"最新 K(9,3,3) = {k[-1]:.2f}")
print(f"最新 D(9,3,3) = {d[-1]:.2f}")
print(f"最新 J(9,3,3) = {j[-1]:.2f}")

# ---------- 3. 可视化 ----------
fig = plt.figure(figsize=(16, 10))
gs = GridSpec(4, 1, figure=fig, height_ratios=[2.5, 1.5, 1.5, 0.3], hspace=0.35)

ax1 = fig.add_subplot(gs[0])   # 股价与买卖信号
ax2 = fig.add_subplot(gs[1])   # KDJ 三线
ax3 = fig.add_subplot(gs[2])   # KDJ 柱状图 (J-K 差异)
ax4 = fig.add_subplot(gs[3])   # 说明

# ----- 3.1 股价走势 -----
ax1.plot(dates, close, color='#d62728', linewidth=1.5, label='收盘价', zorder=3)
# 标注 KDJ 超买超卖区域对应的价格区间
ax1.axhspan(ymin=0, ymax=ax1.get_ylim()[1], xmin=0, xmax=1, alpha=0, color='none')
# 标注 J 值极端区域
ax1.set_title('寒武纪（688256.SH）股价走势', fontsize=14, fontweight='bold')
ax1.set_ylabel('价格（元）')
ax1.legend(loc='upper left', fontsize=9)
ax1.grid(True, alpha=0.2)
ax1.set_xlim(dates[0], dates[-1])

# 标注超买超卖信号点
for i in range(1, len(j)):
    if j[i] > 100:
        ax1.scatter(dates[i], close[i], color='#d62728', s=30, marker='v', zorder=4, alpha=0.6)
    elif j[i] < 0:
        ax1.scatter(dates[i], close[i], color='#2ca02c', s=30, marker='^', zorder=4, alpha=0.6)

# 图例说明
ax1.scatter([], [], color='#d62728', s=30, marker='v', label='J>100 超买')
ax1.scatter([], [], color='#2ca02c', s=30, marker='^', label='J<0 超卖')
ax1.legend(loc='upper left', fontsize=9, ncol=3)

# ----- 3.2 KDJ 三线 -----
ax2.plot(dates, k, color='#1f77b4', linewidth=1.5, label='K值')
ax2.plot(dates, d, color='#ff7f0e', linewidth=1.5, label='D值')
ax2.plot(dates, j, color='#9467bd', linewidth=2.0, label='J值')
ax2.axhline(y=100, color='#d62728', linestyle='--', linewidth=0.8, alpha=0.5)
ax2.axhline(y=80, color='#ff7f0e', linestyle=':', linewidth=0.6, alpha=0.4)
ax2.axhline(y=20, color='#2ca02c', linestyle=':', linewidth=0.6, alpha=0.4)
ax2.axhline(y=0, color='#2ca02c', linestyle='--', linewidth=0.8, alpha=0.5)
ax2.axhline(y=50, color='gray', linestyle=':', linewidth=0.5, alpha=0.3)

ax2.fill_between(dates, 80, 100, alpha=0.08, color='#ff7f0e')
ax2.fill_between(dates, 0, 20, alpha=0.08, color='#2ca02c')
ax2.fill_between(dates, 100, 130, alpha=0.12, color='#d62728')
ax2.fill_between(dates, -20, 0, alpha=0.12, color='#2ca02c')

ax2.set_title('KDJ 随机指标', fontsize=14, fontweight='bold')
ax2.set_ylabel('KDJ')
ax2.set_ylim(-20, 130)
ax2.set_yticks([0, 20, 50, 80, 100])
ax2.legend(loc='upper left', fontsize=9)
ax2.grid(True, alpha=0.2)
ax2.set_xlim(dates[0], dates[-1])

# 区域标注
ax2.text(dates[-1], 115, 'J>100\n极端超买', fontsize=8, color='#d62728', ha='left', va='center')
ax2.text(dates[-1], 90, '超买区', fontsize=8, color='#ff7f0e', ha='left', va='center')
ax2.text(dates[-1], 10, '超卖区', fontsize=8, color='#2ca02c', ha='left', va='center')
ax2.text(dates[-1], -14, 'J<0\n极端超卖', fontsize=8, color='#2ca02c', ha='left', va='center')

# ----- 3.3 KDJ 金叉死叉信号 -----
# K 与 D 的差值
kd_diff = k - d
kd_colors = ['#d62728' if v >= 0 else '#2ca02c' for v in kd_diff]
# 增加 bar 宽度以便在 datetime 坐标下可见
ax3.bar(dates, kd_diff, width=2, color=kd_colors, alpha=0.6, label='K-D差值')
ax3.axhline(y=0, color='black', linewidth=0.5)
ax3.set_title('KDJ 金叉/死叉信号', fontsize=14, fontweight='bold')
ax3.set_ylabel('K-D差值')
ax3.legend(loc='upper left', fontsize=9)
ax3.grid(True, alpha=0.2)
ax3.set_xlim(dates[0], dates[-1])

# ----- 3.4 说明 -----
ax4.axis('off')
legend_text = ("参数：KDJ(9,3,3) | K值=DMA(RSV,3,1) | D值=DMA(K,3,1) | J=3D-2K\n"
               "超买区：K、D值>80 或 J>100 | 超卖区：K、D值<20 或 J<0 | 金叉：K上穿D | 死叉：K下穿D")
ax4.text(0.5, 0.5, legend_text, transform=ax4.transAxes,
         fontsize=10, ha='center', va='center')

# 保存
chart_path = os.path.join(OUTPUT_DIR, 'TASK2_KDJ指标可视化.png')
fig.savefig(chart_path, dpi=300, bbox_inches='tight')
plt.close()

print(f"\nKDJ 可视化已保存至：{chart_path}")
