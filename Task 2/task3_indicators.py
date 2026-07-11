"""
任务三：Python 编程计算 RSI / MACD / 布林带 并输出可视化图形
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import os

# ---------- 配置 ----------
CSV_PATH = r'C:\Users\Administrator\Desktop\量化交易：AI大模型辅助的金融交易策略\Task 1\寒武纪_过去一年日线数据.csv'
OUTPUT_DIR = r'C:\Users\Administrator\Desktop\量化交易：AI大模型辅助的金融交易策略\Task 2'

# 中文字体设置
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

# ---------- 1. 加载数据 ----------
df = pd.read_csv(CSV_PATH, encoding='utf-8-sig')
df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')
df = df.sort_values('trade_date').reset_index(drop=True)
close = df['close'].values
dates = df['trade_date'].values

# ---------- 2. 计算指标 ----------

# ----- 2.1 RSI (14日) -----
def calc_rsi(price, period=14):
    """Wilder 平滑法 RSI"""
    delta = np.diff(price)
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)

    # 初始 SMA
    avg_gain = np.full_like(price, np.nan)
    avg_loss = np.full_like(price, np.nan)
    avg_gain[period] = np.mean(gain[:period])
    avg_loss[period] = np.mean(loss[:period])

    # 递归平滑
    for i in range(period + 1, len(price)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gain[i - 1]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + loss[i - 1]) / period

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

rsi = calc_rsi(close, period=14)

# ----- 2.2 MACD (12, 26, 9) -----
def calc_ema(price, period):
    """指数移动平均（处理 NaN 起始点）"""
    alpha = 2 / (period + 1)
    ema = np.full_like(price, np.nan)
    # 找到第一个有效值的位置
    first_valid = np.where(~np.isnan(price))[0]
    if len(first_valid) == 0:
        return ema
    start = first_valid[0]
    # SMA 初始化
    end_idx = start + period
    if end_idx <= len(price):
        ema[end_idx - 1] = np.nanmean(price[start:end_idx])
        for i in range(end_idx, len(price)):
            ema[i] = price[i] * alpha + ema[i - 1] * (1 - alpha)
    return ema

ema12 = calc_ema(close, 12)
ema26 = calc_ema(close, 26)
dif = ema12 - ema26
dea = calc_ema(dif, 9)
macd_hist = (dif - dea) * 2  # 柱状图常用放大倍数2

# ----- 2.3 布林带 (20, 2) -----
def calc_bollinger(price, period=20, k=2):
    """布林带计算"""
    middle = pd.Series(price).rolling(window=period).mean().values
    std = pd.Series(price).rolling(window=period).std(ddof=0).values
    upper = middle + k * std
    lower = middle - k * std
    return upper, middle, lower

bb_upper, bb_middle, bb_lower = calc_bollinger(close, period=20, k=2)

# 保存指标结果到 CSV
indicator_df = pd.DataFrame({
    'trade_date': dates,
    'close': close,
    'rsi': rsi,
    'ema12': ema12,
    'ema26': ema26,
    'dif': dif,
    'dea': dea,
    'macd_hist': macd_hist,
    'bb_upper': bb_upper,
    'bb_middle': bb_middle,
    'bb_lower': bb_lower
})
indicator_path = os.path.join(OUTPUT_DIR, 'TASK2_技术指标计算结果.csv')
indicator_df.to_csv(indicator_path, index=False, encoding='utf-8-sig')
print(f"指标计算结果已保存至：{indicator_path}")

# ---------- 3. 可视化 ----------
fig = plt.figure(figsize=(16, 12))
gs = GridSpec(3, 1, figure=fig, height_ratios=[3, 2, 2], hspace=0.35)

ax1 = fig.add_subplot(gs[0, 0])  # 股价 + 布林带
ax2 = fig.add_subplot(gs[1, 0])  # RSI
ax3 = fig.add_subplot(gs[2, 0])  # MACD

# ----- 3.1 股价 + 布林带 -----
ax1.plot(dates, close, color='#d62728', linewidth=1.5, label='收盘价', zorder=3)
ax1.plot(dates, bb_upper, color='#333333', linewidth=0.8, linestyle='--', label='上轨 (SMA+2σ)')
ax1.plot(dates, bb_middle, color='#333333', linewidth=1.2, label='中轨 (SMA20)')
ax1.plot(dates, bb_lower, color='#333333', linewidth=0.8, linestyle='--', label='下轨 (SMA-2σ)')
ax1.fill_between(dates, bb_lower, bb_upper, alpha=0.08, color='gray')
ax1.set_title('寒武纪（688256.SH）股价走势与布林带', fontsize=14, fontweight='bold')
ax1.set_ylabel('价格（元）')
ax1.legend(loc='upper left', fontsize=9, ncol=4)
ax1.grid(True, alpha=0.2)
ax1.set_xlim(dates[0], dates[-1])

# ----- 3.2 RSI -----
ax2.plot(dates, rsi, color='#1f77b4', linewidth=1.5, label='RSI(14)')
ax2.axhline(y=70, color='#d62728', linestyle='--', linewidth=0.8, alpha=0.6)
ax2.axhline(y=30, color='#2ca02c', linestyle='--', linewidth=0.8, alpha=0.6)
ax2.axhline(y=50, color='gray', linestyle=':', linewidth=0.5, alpha=0.4)
ax2.fill_between(dates, 70, 100, alpha=0.12, color='#d62728')
ax2.fill_between(dates, 0, 30, alpha=0.12, color='#2ca02c')
ax2.set_title('RSI（相对强弱指标）', fontsize=14, fontweight='bold')
ax2.set_ylabel('RSI')
ax2.set_ylim(0, 100)
ax2.set_yticks([0, 30, 50, 70, 100])
ax2.legend(loc='upper left', fontsize=9)
ax2.grid(True, alpha=0.2)
ax2.set_xlim(dates[0], dates[-1])

# 标注超买超卖区域文字
ax2.text(dates[-1], 95, '超买区', fontsize=9, color='#d62728', ha='left', va='center')
ax2.text(dates[-1], 15, '超卖区', fontsize=9, color='#2ca02c', ha='left', va='center')

# ----- 3.3 MACD -----
ax3.plot(dates, dif, color='#1f77b4', linewidth=1.5, label='DIF (EMA12-EMA26)')
ax3.plot(dates, dea, color='#ff7f0e', linewidth=1.5, label='DEA (EMA9 of DIF)')
# 柱状图：红涨绿跌
hist_colors = ['#d62728' if v >= 0 else '#2ca02c' for v in macd_hist]
ax3.bar(dates, macd_hist, width=0.8, color=hist_colors, alpha=0.6, label='MACD柱 (DIF-DEA)×2')
ax3.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
ax3.set_title('MACD（指数平滑异同移动平均线）', fontsize=14, fontweight='bold')
ax3.set_ylabel('MACD')
ax3.legend(loc='upper left', fontsize=9, ncol=3)
ax3.grid(True, alpha=0.2)
ax3.set_xlim(dates[0], dates[-1])

# 图例说明
fig.text(0.5, 0.02, '指标参数：RSI(14) | MACD(12,26,9) | 布林带(20,2)    数据范围：2025-06-30 至 2026-06-29，共242个交易日',
         ha='center', fontsize=10, fontfamily='SimHei')

# 保存
chart_path = os.path.join(OUTPUT_DIR, 'TASK2_技术指标可视化.png')
fig.savefig(chart_path, dpi=300, bbox_inches='tight')
plt.close()

print(f"技术指标可视化已保存至：{chart_path}")

# ---------- 4. 输出关键数值摘要（供报告参考）----------
print("\n===== 指标计算摘要 =====")
last_idx = -1
print(f"最新RSI(14) = {rsi[last_idx]:.2f}")
print(f"最新DIF = {dif[last_idx]:.2f}")
print(f"最新DEA = {dea[last_idx]:.2f}")
print(f"最新MACD柱 = {macd_hist[last_idx]:.2f}")
print(f"最新布林上轨 = {bb_upper[last_idx]:.2f}")
print(f"最新布林中轨 = {bb_middle[last_idx]:.2f}")
print(f"最新布林下轨 = {bb_lower[last_idx]:.2f}")
