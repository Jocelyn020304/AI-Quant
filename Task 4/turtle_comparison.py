"""
Task 4 - 海龟策略多参数多股票对比分析
对不同股票和不同通道周期进行回测，观察收益变化
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import os
from matplotlib.gridspec import GridSpec

matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
matplotlib.rcParams['axes.unicode_minus'] = False

OUT_DIR = r'C:\Users\Administrator\Desktop\量化交易：AI大模型辅助的金融交易策略\Task 4'

STOCK_FILES = {
    '寒武纪（688256.SH）': r'C:\Users\Administrator\Desktop\量化交易：AI大模型辅助的金融交易策略\Task 1\寒武纪_过去一年日线数据.csv',
    '宁德时代（300750.SZ）': r'C:\Users\Administrator\Desktop\量化交易：AI大模型辅助的金融交易策略\Task 3\stock_data\宁德时代_日线数据.csv',
    '贵州茅台（600519.SH）': r'C:\Users\Administrator\Desktop\量化交易：AI大模型辅助的金融交易策略\Task 3\stock_data\贵州茅台_日线数据.csv',
}

PERIODS = [10, 20, 30, 50]
ATR_PERIOD = 14
RISK_RATIO = 0.01
STOP_MULTIPLIER = 2.0
INITIAL_CAPITAL = 1_000_000


def load_data(filepath):
    df = pd.read_csv(filepath)
    if 'trade_date' in df.columns:
        df['trade_date'] = pd.to_datetime(df['trade_date'])
    return df.sort_values('trade_date').reset_index(drop=True)


def backtest_turtle(df, period):
    """对单个股票执行海龟策略回测，返回绩效指标字典"""
    df = df.copy()

    # 唐奇安通道
    df['upper'] = df['high'].rolling(window=period).max()
    df['lower'] = df['low'].rolling(window=period).min()

    # ATR
    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            (df['high'] - df['close'].shift(1)).abs(),
            (df['low'] - df['close'].shift(1)).abs()
        )
    )
    df['atr'] = df['tr'].rolling(window=ATR_PERIOD).mean()

    # 交易信号
    df['buy_signal'] = (df['close'] > df['upper'].shift(1)) & (df['close'].shift(1) <= df['upper'].shift(2))
    df['sell_signal'] = (df['close'] < df['lower'].shift(1)) & (df['close'].shift(1) >= df['lower'].shift(2))

    # 回测
    position = 0
    entry_price = 0.0
    cash = INITIAL_CAPITAL
    shares = 0
    trades = 0
    trade_log = []
    equity = [1.0]
    win_count = 0
    loss_count = 0

    start_idx = max(period, ATR_PERIOD)

    for i in range(start_idx, len(df)):
        row = df.iloc[i]
        close = row['close']
        atr_val = row['atr']

        if pd.isna(atr_val) or atr_val <= 0:
            current_equity = cash + shares * close
            equity.append(current_equity / INITIAL_CAPITAL)
            continue

        # 止损
        if position == 1:
            stop_price = entry_price - STOP_MULTIPLIER * atr_val
            if close < stop_price:
                revenue = shares * close
                cash += revenue
                profit = revenue - shares * entry_price
                if profit > 0:
                    win_count += 1
                else:
                    loss_count += 1
                trade_log.append((i, '止损卖出', close, shares, profit))
                shares = 0
                position = 0
                trades += 1

        # 买入
        if row['buy_signal'] and position == 0:
            risk_amount = cash * RISK_RATIO
            unit = max(1, int(risk_amount / atr_val))
            cost = unit * close
            if cost <= cash:
                shares = unit
                cash -= cost
                entry_price = close
                position = 1
                trade_log.append((i, '买入', close, unit, 0))
                trades += 1

        # 卖出
        elif row['sell_signal'] and position == 1:
            revenue = shares * close
            cash += revenue
            profit = revenue - shares * entry_price
            if profit > 0:
                win_count += 1
            else:
                loss_count += 1
            trade_log.append((i, '卖出', close, shares, profit))
            shares = 0
            position = 0
            trades += 1

        current_equity = cash + shares * close
        equity.append(current_equity / INITIAL_CAPITAL)

    # 期末平仓
    if position == 1:
        close = df.iloc[-1]['close']
        revenue = shares * close
        cash += revenue
        profit = revenue - shares * entry_price
        if profit > 0:
            win_count += 1
        else:
            loss_count += 1
        trade_log.append((len(df) - 1, '期末平仓', close, shares, profit))
        shares = 0
        position = 0

    while len(equity) < len(df) - start_idx + 1:
        equity.append(equity[-1])

    equity_series = pd.Series(equity)

    # 绩效指标
    cumulative_return = equity_series.iloc[-1] - 1
    trading_days = len(equity_series) - 1
    annual_return = equity_series.iloc[-1] ** (242 / trading_days) - 1 if trading_days > 0 else 0

    peak = equity_series.cummax()
    drawdown = (equity_series - peak) / peak
    max_drawdown = drawdown.min()

    daily_returns = equity_series.pct_change().dropna()
    annual_vol = daily_returns.std() * np.sqrt(242)

    risk_free = 0.02
    sharpe = (annual_return - risk_free) / annual_vol if annual_vol > 0 else 0

    n_trades = len([t for t in trade_log if t[1] in ('卖出', '止损卖出', '期末平仓')])
    win_rate = win_count / n_trades if n_trades > 0 else 0

    return {
        '累计回报': cumulative_return,
        '年化收益率': annual_return,
        '年化波动率': annual_vol,
        '最大回撤': max_drawdown,
        '夏普比率': sharpe,
        '交易次数': n_trades,
        '胜率': win_rate,
        '净值序列': equity_series,
        '买入信号次数': df['buy_signal'].sum(),
        '卖出信号次数': df['sell_signal'].sum(),
    }


# ========== 执行回测 ==========
results = {}

for stock_name, filepath in STOCK_FILES.items():
    df = load_data(filepath)
    for period in PERIODS:
        key = (stock_name, period)
        print(f"回测中：{stock_name}，通道周期={period}...")
        results[key] = backtest_turtle(df, period)

# ---------- 输出汇总表 ----------
rows = []
for (stock_name, period), metrics in results.items():
    rows.append({
        '股票': stock_name,
        '通道周期': period,
        '累计回报': f"{metrics['累计回报']:.2%}",
        '年化收益率': f"{metrics['年化收益率']:.2%}",
        '年化波动率': f"{metrics['年化波动率']:.2%}",
        '最大回撤': f"{metrics['最大回撤']:.2%}",
        '夏普比率': f"{metrics['夏普比率']:.2f}",
        '交易次数': metrics['交易次数'],
        '胜率': f"{metrics['胜率']:.1%}",
    })

summary_df = pd.DataFrame(rows)
csv_path = os.path.join(OUT_DIR, 'TASK4_多股票多参数回测对比.csv')
summary_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
print(f"\n对比数据已保存至：{csv_path}")
print(summary_df.to_string(index=False))

# ---------- 可视化 ----------
fig = plt.figure(figsize=(16, 14))
gs = GridSpec(3, 2, figure=fig, hspace=0.35, wspace=0.3)

color_map = {10: '#e74c3c', 20: '#e67e22', 30: '#2ecc71', 50: '#3498db'}
stock_colors = {'寒武纪（688256.SH）': '#e74c3c', '宁德时代（300750.SZ）': '#2ecc71', '贵州茅台（600519.SH）': '#3498db'}
period_labels = {10: 'MA10', 20: 'MA20', 30: 'MA30', 50: 'MA50'}

# 第一行：各股票在不同周期下的夏普比率对比（柱状图）
ax1 = fig.add_subplot(gs[0, 0])
x = np.arange(len(PERIODS))
width = 0.25
for idx, (stock_name, _) in enumerate(results):
    pass

for i, stock_name in enumerate(STOCK_FILES.keys()):
    sharpe_vals = [results[(stock_name, p)]['夏普比率'] for p in PERIODS]
    ax1.bar(x + i * width, sharpe_vals, width, label=stock_name, color=list(stock_colors.values())[i], alpha=0.8)
ax1.set_xticks(x + width)
ax1.set_xticklabels([f'{p}日' for p in PERIODS])
ax1.set_ylabel('夏普比率')
ax1.set_title('不同通道周期下各股票夏普比率对比')
ax1.legend(fontsize=8)
ax1.axhline(y=0, color='gray', linestyle=':', linewidth=0.5)
ax1.grid(True, alpha=0.3, axis='y')

# 第二行左：各股票在20日周期下的净值曲线对比
ax2 = fig.add_subplot(gs[0, 1])
for stock_name in STOCK_FILES.keys():
    eq = results[(stock_name, 20)]['净值序列']
    ax2.plot(eq.values, label=stock_name, color=stock_colors[stock_name], linewidth=1.2)
ax2.set_title('20日通道周期下各股票策略净值对比')
ax2.set_ylabel('净值')
ax2.axhline(y=1.0, color='gray', linestyle=':', linewidth=0.5)
ax2.legend(fontsize=8)
ax2.grid(True, alpha=0.3)

# 第二行右：寒武纪在不同周期下的累计回报
ax3 = fig.add_subplot(gs[1, 0])
cumu_vals = [results[('寒武纪（688256.SH）', p)]['累计回报'] for p in PERIODS]
bars = ax3.bar(x, cumu_vals, width=0.5, color=[color_map[p] for p in PERIODS], alpha=0.8)
for bar, val in zip(bars, cumu_vals):
    ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + (0.01 if val >= 0 else -0.05),
             f'{val:.1%}', ha='center', va='bottom' if val >= 0 else 'top', fontsize=9)
ax3.set_xticks(x)
ax3.set_xticklabels([f'{p}日' for p in PERIODS])
ax3.set_ylabel('累计回报')
ax3.set_title('寒武纪：不同通道周期累计回报对比')
ax3.axhline(y=0, color='gray', linestyle=':', linewidth=0.5)
ax3.grid(True, alpha=0.3, axis='y')

# 第三行左：宁德时代在不同周期下的累计回报
ax4 = fig.add_subplot(gs[1, 1])
cumu_vals2 = [results[('宁德时代（300750.SZ）', p)]['累计回报'] for p in PERIODS]
bars2 = ax4.bar(x, cumu_vals2, width=0.5, color=[color_map[p] for p in PERIODS], alpha=0.8)
for bar, val in zip(bars2, cumu_vals2):
    ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + (0.01 if val >= 0 else -0.05),
             f'{val:.1%}', ha='center', va='bottom' if val >= 0 else 'top', fontsize=9)
ax4.set_xticks(x)
ax4.set_xticklabels([f'{p}日' for p in PERIODS])
ax4.set_ylabel('累计回报')
ax4.set_title('宁德时代：不同通道周期累计回报对比')
ax4.axhline(y=0, color='gray', linestyle=':', linewidth=0.5)
ax4.grid(True, alpha=0.3, axis='y')

# 第三行：贵州茅台净值曲线（不同周期）
ax5 = fig.add_subplot(gs[2, 0])
for p in PERIODS:
    eq = results[('贵州茅台（600519.SH）', p)]['净值序列']
    ax5.plot(eq.values, label=f'{p}日周期', color=color_map[p], linewidth=1.0)
ax5.set_title('贵州茅台：不同通道周期净值曲线')
ax5.set_ylabel('净值')
ax5.set_xlabel('交易日')
ax5.axhline(y=1.0, color='gray', linestyle=':', linewidth=0.5)
ax5.legend(fontsize=8)
ax5.grid(True, alpha=0.3)

# 第三行右：各股票最大回撤对比
ax6 = fig.add_subplot(gs[2, 1])
x2 = np.arange(len(PERIODS))
for i, stock_name in enumerate(STOCK_FILES.keys()):
    mdd_vals = [results[(stock_name, p)]['最大回撤'] for p in PERIODS]
    ax6.plot(x2, mdd_vals, marker='o', label=stock_name, color=list(stock_colors.values())[i], linewidth=1.5)
ax6.set_xticks(x2)
ax6.set_xticklabels([f'{p}日' for p in PERIODS])
ax6.set_ylabel('最大回撤')
ax6.set_title('最大回撤对比')
ax6.legend(fontsize=8)
ax6.grid(True, alpha=0.3)

plt.suptitle('海龟策略多参数多股票回测对比分析', fontsize=16, fontweight='bold', y=0.98)
plt.savefig(os.path.join(OUT_DIR, 'TASK4_多参数多股票对比分析.png'), dpi=300, bbox_inches='tight')
plt.close()
print(f"对比分析图已保存")
