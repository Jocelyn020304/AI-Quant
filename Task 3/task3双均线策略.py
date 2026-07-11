"""
Task 3 — 双均线策略：Python 实现与回测
1) 加载股价数据
2) 计算短/长均线
3) 生成买卖信号（金叉/死叉）
4) 可视化：股价 + 均线 + 信号标记
5) 回测与量化指标：累计回报、MDD、夏普比率
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import matplotlib.dates as mdates
import os

# ---------- 配置 ----------
CSV_PATH = r'C:\Users\Administrator\Desktop\量化交易：AI大模型辅助的金融交易策略\Task 1\寒武纪_过去一年日线数据.csv'
OUT_DIR = r'C:\Users\Administrator\Desktop\量化交易：AI大模型辅助的金融交易策略\Task 3'

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

# ---------- 1. 加载数据 ----------
df = pd.read_csv(CSV_PATH, encoding='utf-8-sig')
df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')
df = df.sort_values('trade_date').reset_index(drop=True)

dates = df['trade_date'].values
close = df['close'].values
N = len(df)

# ---------- 2. 设定均线周期并计算 ----------
short_win = 5
long_win = 15

def calc_sma(data, window):
    """简单移动平均"""
    return pd.Series(data).rolling(window=window).mean().values

ma_short = calc_sma(close, short_win)
ma_long = calc_sma(close, long_win)

print("===== 均线计算结果（最新10期） =====")
print(f"参数：短均线 = MA{short_win}，长均线 = MA{long_win}")
for i in range(max(-10, -N), 0):
    d = dates[i]
    print(f"{pd.Timestamp(d).strftime('%Y-%m-%d'):>12s}  收盘价={close[i]:>8.2f}  MA{short_win}={ma_short[i]:>8.2f}  MA{long_win}={ma_long[i]:>8.2f}")

# ---------- 3. 生成交易信号 ----------
# 信号规则：短期均线上穿长期均线 → 买入(1)；下穿 → 卖出(-1)；其余 → 持有(0)
signal = np.zeros(N, dtype=int)

for i in range(1, N):
    if np.isnan(ma_short[i]) or np.isnan(ma_long[i]):
        continue
    if np.isnan(ma_short[i-1]) or np.isnan(ma_long[i-1]):
        continue
    if ma_short[i-1] <= ma_long[i-1] and ma_short[i] > ma_long[i]:
        signal[i] = 1   # 金叉 → 买入
    elif ma_short[i-1] >= ma_long[i-1] and ma_short[i] < ma_long[i]:
        signal[i] = -1  # 死叉 → 卖出

buy_signals = dates[signal == 1]
buy_prices = close[signal == 1]
sell_signals = dates[signal == -1]
sell_prices = close[signal == -1]

print(f"\n===== 交易信号 =====")
print(f"买入信号（金叉）次数：{len(buy_signals)}")
print(f"卖出信号（死叉）次数：{len(sell_signals)}")
for idx in np.where(signal != 0)[0]:
    typ = "买入" if signal[idx] == 1 else "卖出"
    print(f"{pd.Timestamp(dates[idx]).strftime('%Y-%m-%d'):>12s}  {typ}  价格={close[idx]:>8.2f}")

# ---------- 4. 可视化 ----------
fig = plt.figure(figsize=(18, 12))
gs = GridSpec(3, 1, figure=fig, height_ratios=[3, 1.5, 1.5], hspace=0.3)

# ----- 4.1 主图：股价 + 均线 + 信号 -----
ax1 = fig.add_subplot(gs[0])
ax1.plot(dates, close, color='#333333', linewidth=1.2, label='收盘价', alpha=0.8)
ax1.plot(dates, ma_short, color='#d62728', linewidth=1.5, label=f'MA{short_win}（短期均线）')
ax1.plot(dates, ma_long, color='#1f77b4', linewidth=1.5, label=f'MA{long_win}（长期均线）')

# 买入信号标记
ax1.scatter(buy_signals, buy_prices, color='#d62728', s=120,
            marker='^', zorder=5, label='买入（金叉）', edgecolors='black', linewidth=0.5)
# 卖出信号标记
ax1.scatter(sell_signals, sell_prices, color='#2ca02c', s=120,
            marker='v', zorder=5, label='卖出（死叉）', edgecolors='black', linewidth=0.5)

ax1.set_title(f'寒武纪（688256.SH）双均线策略 — MA{short_win} / MA{long_win}', fontsize=14, fontweight='bold')
ax1.set_ylabel('价格（元）')
ax1.legend(loc='upper left', fontsize=10, ncol=2)
ax1.grid(True, alpha=0.2)
ax1.set_xlim(dates[0], dates[-1])
ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
ax1.tick_params(axis='x', rotation=30)

# ----- 4.2 资金曲线 -----
ax2 = fig.add_subplot(gs[1])
# 模拟交易：初始资金1元，全仓买卖
position = 0  # 0空仓，1持仓
equity = np.ones(N)  # 净值曲线

for i in range(N):
    if i == 0:
        continue
    if signal[i] == 1 and position == 0:
        position = 1
        entry_idx = i
    elif signal[i] == -1 and position == 1:
        position = 0
        # 卖出：累计收益
        equity[i:] = equity[i:] * (close[i] / close[entry_idx])

# 处理最后仍持仓的情况
if position == 1:
    equity[-1] = equity[-1] * (close[-1] / close[entry_idx])

ax2.plot(dates, equity, color='#d62728', linewidth=1.5, label='策略净值')
ax2.axhline(y=1.0, color='gray', linestyle='--', linewidth=0.8, alpha=0.5)
ax2.set_title('策略净值曲线', fontsize=14, fontweight='bold')
ax2.set_ylabel('净值')
ax2.legend(loc='upper left', fontsize=10)
ax2.grid(True, alpha=0.2)
ax2.set_xlim(dates[0], dates[-1])
ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
ax2.tick_params(axis='x', rotation=30)

# ----- 4.3 回撤曲线 -----
ax3 = fig.add_subplot(gs[2])
rolling_max = np.maximum.accumulate(equity)
drawdown = (equity - rolling_max) / rolling_max

ax3.fill_between(dates, 0, drawdown, color='#2ca02c', alpha=0.4, label='回撤')
ax3.plot(dates, drawdown, color='#2ca02c', linewidth=1.0)
ax3.axhline(y=0, color='gray', linestyle='-', linewidth=0.5)
ax3.set_title('策略回撤曲线', fontsize=14, fontweight='bold')
ax3.set_ylabel('回撤幅度')
ax3.set_ylim(min(drawdown) - 0.05, 0.05)
ax3.legend(loc='lower left', fontsize=10)
ax3.grid(True, alpha=0.2)
ax3.set_xlim(dates[0], dates[-1])
ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
ax3.tick_params(axis='x', rotation=30)

chart_path = os.path.join(OUT_DIR, 'TASK3_双均线策略回测可视化.png')
fig.savefig(chart_path, dpi=300, bbox_inches='tight')
plt.close()
print(f"\n可视化已保存至：{chart_path}")

# ---------- 5. 量化指标计算 ----------
# 5.1 累计回报
total_return = equity[-1] - 1.0
print(f"\n===== 量化绩效指标 =====")
print(f"累计回报：{total_return * 100:.2f}%")

# 5.2 最大回撤
mdd = np.min(drawdown)
print(f"最大回撤（MDD）：{mdd * 100:.2f}%")

# 5.3 夏普比率（年化）
# 日收益率
daily_returns = np.diff(equity) / equity[:-1]
# 年化收益率（252个交易日）
annual_return = np.mean(daily_returns) * 252
# 年化波动率
annual_vol = np.std(daily_returns, ddof=1) * np.sqrt(252)
# 无风险利率取 2%（年化）
risk_free = 0.02
sharpe = (annual_return - risk_free) / annual_vol if annual_vol > 0 else 0

print(f"年化收益率：{annual_return * 100:.2f}%")
print(f"年化波动率：{annual_vol * 100:.2f}%")
print(f"夏普比率（$R_f=2\\%$）：{sharpe:.4f}")

# ---------- 导出计算结果 ----------
results = {
    '指标': ['累计回报', '最大回撤(MDD)', '年化收益率', '年化波动率', '夏普比率', '买入信号次数', '卖出信号次数'],
    '数值': [f'{total_return*100:.2f}%', f'{mdd*100:.2f}%', f'{annual_return*100:.2f}%',
             f'{annual_vol*100:.2f}%', f'{sharpe:.4f}', str(len(buy_signals)), str(len(sell_signals))]
}
results_df = pd.DataFrame(results)
results_csv = os.path.join(OUT_DIR, 'TASK3_回测绩效指标.csv')
results_df.to_csv(results_csv, index=False, encoding='utf-8-sig')
print(f"\n回测绩效指标已保存至：{results_csv}")
print("\n", results_df.to_string(index=False))
