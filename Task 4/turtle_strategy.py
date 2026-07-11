"""
Task 4 - 海龟交易策略的 Python 实现与回测
功能：加载寒武纪股价数据 → 计算唐奇安通道(20) → 计算ATR(14) → 生成交易信号
      → 可视化 → 策略回测与绩效指标计算
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import os

# ---------- 中文字体 ----------
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
matplotlib.rcParams['axes.unicode_minus'] = False

# ---------- 路径 ----------
DATA_PATH = r'C:\Users\Administrator\Desktop\量化交易：AI大模型辅助的金融交易策略\Task 1\寒武纪_过去一年日线数据.csv'
OUT_DIR = r'C:\Users\Administrator\Desktop\量化交易：AI大模型辅助的金融交易策略\Task 4'
CHART_PATH = os.path.join(OUT_DIR, 'TASK4_海龟策略回测可视化.png')
CSV_PATH = os.path.join(OUT_DIR, 'TASK4_海龟策略回测指标.csv')

# ---------- 1. 加载数据 ----------
df = pd.read_csv(DATA_PATH)
df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')
df.sort_values('trade_date', inplace=True)
df.reset_index(drop=True, inplace=True)

# ---------- 2. 计算唐奇安通道（20日） ----------
period = 20
df['upper'] = df['high'].rolling(window=period).max()
df['lower'] = df['low'].rolling(window=period).min()
df['middle'] = (df['upper'] + df['lower']) / 2

# ---------- 3. 计算 ATR（14日） ----------
atr_period = 14
df['tr'] = np.maximum(
    df['high'] - df['low'],
    np.maximum(
        (df['high'] - df['close'].shift(1)).abs(),
        (df['low'] - df['close'].shift(1)).abs()
    )
)
df['atr'] = df['tr'].rolling(window=atr_period).mean()

# ---------- 4. 生成交易信号 ----------
# 买入信号：收盘价上穿上轨
df['buy_signal'] = (df['close'] > df['upper'].shift(1)) & (df['close'].shift(1) <= df['upper'].shift(2))
# 卖出信号：收盘价下穿下轨
df['sell_signal'] = (df['close'] < df['lower'].shift(1)) & (df['close'].shift(1) >= df['lower'].shift(2))

# ---------- 5. 策略回测 ----------
position = 0         # 当前持仓：0空仓，1持仓
entry_price = 0.0
trade_log = []       # [(日期, 类型, 价格, 数量)]
equity = [1.0]       # 净值序列（初始净值1）
initial_capital = 1_000_000
cash = initial_capital
shares = 0
trades = 0
total_profit = 0

# 回测循环：从第21行开始（前20行无通道数据）
for i in range(period, len(df)):
    row = df.iloc[i]
    close = row['close']
    date = row['trade_date']
    atr_val = row['atr']

    # 检查止损（持仓中）
    if position == 1 and entry_price > 0:
        stop_price = entry_price - 2 * atr_val
        if close < stop_price:
            # 止损卖出
            revenue = shares * close
            cash += revenue
            profit = revenue - shares * entry_price
            total_profit += profit
            trade_log.append((date, '止损卖出', close, shares))
            shares = 0
            position = 0
            trades += 1

    # 买入信号
    if row['buy_signal'] and position == 0:
        # 计算仓位：账户权益 1% / (ATR * 每手乘数)
        risk_amount = cash * 0.01
        unit = max(1, int(risk_amount / atr_val)) if atr_val > 0 else 1
        cost = unit * close
        if cost <= cash:
            shares = unit
            cash -= cost
            entry_price = close
            position = 1
            trade_log.append((date, '买入', close, unit))
            trades += 1

    # 卖出信号
    elif row['sell_signal'] and position == 1:
        revenue = shares * close
        cash += revenue
        profit = revenue - shares * entry_price
        total_profit += profit
        trade_log.append((date, '卖出', close, shares))
        shares = 0
        position = 0
        trades += 1

    # 记录当前净值
    current_equity = cash + shares * close
    equity.append(current_equity / initial_capital)

# 最后平仓（如有持仓）
if position == 1:
    close = df.iloc[-1]['close']
    revenue = shares * close
    cash += revenue
    total_profit += revenue - shares * entry_price
    trade_log.append((df.iloc[-1]['trade_date'], '期末平仓', close, shares))
    shares = 0
    position = 0

# 补全净值序列长度
while len(equity) < len(df) - period + 1:
    equity.append(equity[-1])

# ---------- 6. 计算绩效指标 ----------
equity_series = pd.Series(equity)

# 累计回报
cumulative_return = equity_series.iloc[-1] - 1

# 年化收益率（约242个交易日）
trading_days = len(equity_series) - 1
annual_return = equity_series.iloc[-1] ** (242 / trading_days) - 1 if trading_days > 0 else 0

# 最大回撤
peak = equity_series.cummax()
drawdown = (equity_series - peak) / peak
max_drawdown = drawdown.min()

# 年化波动率
daily_returns = equity_series.pct_change().dropna()
annual_vol = daily_returns.std() * np.sqrt(242)

# 夏普比率（无风险利率取 2%）
risk_free = 0.02
sharpe = (annual_return - risk_free) / annual_vol if annual_vol > 0 else 0

# 胜率
win_trades = [t for t in trade_log if '卖出' in t[1] or '止损' in t[1] or '期末' in t[1]]
if trades > 0:
    # 粗略统计：根据买卖配对估算
    win_rate = np.nan
else:
    win_rate = np.nan

# ---------- 7. 可视化 ----------
fig = plt.figure(figsize=(14, 10))
gs = fig.add_gridspec(3, 1, height_ratios=[3, 1.2, 1.2], hspace=0.25)

# 第一面板：股价 + 唐奇安通道 + 交易信号
ax1 = fig.add_subplot(gs[0])
ax1.plot(df['trade_date'], df['close'], label='收盘价', color='#333333', linewidth=1.2)
ax1.plot(df['trade_date'], df['upper'], label=f'上轨({period}日高)', color='#e74c3c', linewidth=0.8, linestyle='--')
ax1.plot(df['trade_date'], df['lower'], label=f'下轨({period}日低)', color='#27ae60', linewidth=0.8, linestyle='--')
ax1.fill_between(df['trade_date'], df['upper'], df['lower'], alpha=0.08, color='gray')

# 标记买入信号
buy_dates = df[df['buy_signal']]['trade_date']
buy_prices = df[df['buy_signal']]['close']
ax1.scatter(buy_dates, buy_prices, marker='^', color='red', s=120, label='买入信号', zorder=5)

# 标记卖出信号
sell_dates = df[df['sell_signal']]['trade_date']
sell_prices = df[df['sell_signal']]['close']
ax1.scatter(sell_dates, sell_prices, marker='v', color='green', s=120, label='卖出信号', zorder=5)

ax1.set_title('寒武纪（688256.SH）海龟策略交易信号', fontsize=13, fontweight='bold')
ax1.set_ylabel('价格（元）')
ax1.legend(loc='upper left', fontsize=8, ncol=3)
ax1.grid(True, alpha=0.3)

# 第二面板：ATR
ax2 = fig.add_subplot(gs[1])
ax2.bar(df['trade_date'], df['atr'], color='#9b59b6', alpha=0.7, width=1.5, label=f'ATR({atr_period})')
ax2.set_ylabel('ATR')
ax2.legend(loc='upper left', fontsize=9)
ax2.grid(True, alpha=0.3)

# 第三面板：策略净值曲线
ax3 = fig.add_subplot(gs[2])
x_vals = df['trade_date'].iloc[period-1:period-1+len(equity_series)].values
ax3.plot(x_vals, equity_series.values, color='#e67e22', linewidth=1.5, label='策略净值')
ax3.axhline(y=1.0, color='gray', linestyle=':', linewidth=0.8)
ax3.fill_between(x_vals, 1.0, equity_series.values, where=equity_series.values >= 1.0,
                 alpha=0.2, color='red')
ax3.fill_between(x_vals, 1.0, equity_series.values, where=equity_series.values < 1.0,
                 alpha=0.2, color='green')
ax3.set_ylabel('净值')
ax3.set_xlabel('交易日期')
ax3.legend(loc='upper left', fontsize=9)
ax3.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(CHART_PATH, dpi=300, bbox_inches='tight')
plt.close()
print(f"图表已保存至：{CHART_PATH}")

# ---------- 8. 导出回测指标 ----------
metrics = pd.DataFrame({
    '指标': ['累计回报', '年化收益率', '年化波动率', '最大回撤', '夏普比率', '交易次数', '数据起始日', '数据截止日'],
    '数值': [
        f'{cumulative_return:.2%}',
        f'{annual_return:.2%}',
        f'{annual_vol:.2%}',
        f'{max_drawdown:.2%}',
        f'{sharpe:.2f}',
        trades,
        df['trade_date'].iloc[0].strftime('%Y-%m-%d'),
        df['trade_date'].iloc[-1].strftime('%Y-%m-%d')
    ]
})
metrics.to_csv(CSV_PATH, index=False, encoding='utf-8-sig')
print(f"回测指标已保存至：{CSV_PATH}")

# ---------- 9. 输出汇总 ----------
print(f"\n===== 海龟策略回测结果 =====")
print(f"累计回报：{cumulative_return:.2%}")
print(f"年化收益率：{annual_return:.2%}")
print(f"年化波动率：{annual_vol:.2%}")
print(f"最大回撤：{max_drawdown:.2%}")
print(f"夏普比率：{sharpe:.2f}")
print(f"交易次数：{trades}")
print(f"交易日志（共{len(trade_log)}笔）：")
for t in trade_log:
    print(f"  {t[0].strftime('%Y-%m-%d')} | {t[1]} | 价格: {t[2]:.2f} | 数量: {t[3]}")
