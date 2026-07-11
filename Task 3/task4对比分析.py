"""
Task 4 — 不同股票与均线周期双均线策略对比分析
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import os

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

OUT_DIR = r'C:\Users\Administrator\Desktop\量化交易：AI大模型辅助的金融交易策略\Task 3'
DATA_DIR = r'C:\Users\Administrator\Desktop\量化交易：AI大模型辅助的金融交易策略\Task 3\stock_data'

os.makedirs(DATA_DIR, exist_ok=True)

# ---------- 1. 构建宁德时代和茅台的日线数据 ----------
# 寒武纪直接从Task 1读取
hw_src = r'C:\Users\Administrator\Desktop\量化交易：AI大模型辅助的金融交易策略\Task 1\寒武纪_过去一年日线数据.csv'

# 宁德时代和茅台：用MCP获取的数据构建CSV
# 从MCP返回的数据中提取完整close序列用于回测
# 注意：这里使用从Tushare MCP获取的全部数据

# 先写出脚本，由用户确认数据存在后再运行
print("===== 双均线策略多股票多参数对比分析 =====")
print(f"工作目录: {OUT_DIR}")
print(f"数据目录: {DATA_DIR}")

# ---------- 回测核心函数 ----------
def backtest_ma(close, short_win, long_win):
    n = len(close)
    if n < max(short_win, long_win) + 5:
        return None
    close_s = pd.Series(close)
    ma_short = close_s.rolling(window=short_win).mean().values
    ma_long = close_s.rolling(window=long_win).mean().values

    signal = np.zeros(n, dtype=int)
    for i in range(1, n):
        if np.isnan(ma_short[i]) or np.isnan(ma_long[i]):
            continue
        if np.isnan(ma_short[i-1]) or np.isnan(ma_long[i-1]):
            continue
        if ma_short[i-1] <= ma_long[i-1] and ma_short[i] > ma_long[i]:
            signal[i] = 1
        elif ma_short[i-1] >= ma_long[i-1] and ma_short[i] < ma_long[i]:
            signal[i] = -1

    position = 0
    equity = np.ones(n)
    entry_idx = 0
    for i in range(1, n):
        if signal[i] == 1 and position == 0:
            position = 1
            entry_idx = i
        elif signal[i] == -1 and position == 1:
            position = 0
            equity[i:] = equity[i:] * (close[i] / close[entry_idx])
    if position == 1:
        eq_ratio = close[-1] / close[entry_idx] if entry_idx > 0 else 1.0
        equity[-1] = equity[-1] * eq_ratio

    total_return = equity[-1] - 1.0
    rolling_max = np.maximum.accumulate(equity)
    drawdown = (equity - rolling_max) / rolling_max
    mdd = np.min(drawdown)

    daily_ret = np.diff(equity) / equity[:-1]
    if len(daily_ret) > 0 and np.std(daily_ret, ddof=1) > 0:
        ann_ret = np.mean(daily_ret) * 252
        ann_vol = np.std(daily_ret, ddof=1) * np.sqrt(252)
        sharpe = (ann_ret - 0.02) / ann_vol if ann_vol > 0 else 0
    else:
        ann_ret = 0; ann_vol = 0; sharpe = 0

    return {
        'cum_return': total_return, 'mdd': mdd,
        'ann_return': ann_ret, 'ann_vol': ann_vol,
        'sharpe': sharpe,
        'n_buy': int(np.sum(signal == 1)), 'n_sell': int(np.sum(signal == -1)),
        'equity': equity, 'drawdown': drawdown, 'signal': signal,
        'ma_short': ma_short, 'ma_long': ma_long
    }

# ---------- 加载寒武纪数据 ----------
hw_df = pd.read_csv(hw_src, encoding='utf-8-sig')
hw_df['trade_date'] = pd.to_datetime(hw_df['trade_date'], format='%Y%m%d')
hw_df = hw_df.sort_values('trade_date').reset_index(drop=True)
hw_close = hw_df['close'].values
hw_dates = hw_df['trade_date'].values
print(f"\n寒武纪: {len(hw_df)}个交易日 ({pd.Timestamp(hw_dates[0]).date()} ~ {pd.Timestamp(hw_dates[-1]).date()}), 均价={hw_close.mean():.2f}")

# ---------- 加载宁德时代和茅台（如存在） ----------
stock_data = {}
for fname in ['宁德时代_日线数据.csv', '贵州茅台_日线数据.csv']:
    fpath = os.path.join(DATA_DIR, fname)
    if os.path.exists(fpath):
        df = pd.read_csv(fpath, encoding='utf-8-sig')
        if 'trade_date' in df.columns:
            df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')
        df = df.sort_values('trade_date').reset_index(drop=True)
        stock_data[fname.replace('_日线数据.csv', '')] = df
        print(f"{fname.replace('_日线数据.csv','')}: {len(df)}个交易日, 均价={df['close'].mean():.2f}")
    else:
        print(f"⚠️ {fname} 未找到，该股票将被跳过")

# ---------- 寒武纪：多参数回测 ----------
param_sets = [(5, 15), (10, 30), (20, 60), (5, 20), (10, 20), (10, 60)]
all_results = []

print(f"\n{'='*65}")
print(f"{'寒武纪(688256.SH) 不同均线参数回测对比':^65}")
print(f"{'='*65}")
print(f"{'参数':>8}  {'累计回报':>8}  {'最大回撤':>8}  {'夏普比率':>8}  {'年化收益':>8}  {'年化波动':>8}  {'交易次数':>8}")
print(f"{'-'*65}")

for sw, lw in param_sets:
    res = backtest_ma(hw_close, sw, lw)
    if res is None: continue
    all_results.append({
        '股票': '寒武纪', '参数': f'MA{sw}/{lw}',
        '累计回报': res['cum_return']*100,
        '最大回撤': res['mdd']*100,
        '年化收益': res['ann_return']*100,
        '年化波动': res['ann_vol']*100,
        '夏普比率': res['sharpe'],
        '交易次数': res['n_buy']+res['n_sell']
    })
    print(f"{f'MA{sw}/{lw}':>8}  {res['cum_return']*100:>7.2f}%  {res['mdd']*100:>7.2f}%  {res['sharpe']:>8.4f}  {res['ann_return']*100:>7.2f}%  {res['ann_vol']*100:>7.2f}%  {res['n_buy']+res['n_sell']:>8}")

# ---------- 不同股票：相同参数(MA10/30)对比 ----------
if '宁德时代' in stock_data and '贵州茅台' in stock_data:
    print(f"\n{'='*65}")
    print(f"{'不同股票相同参数(MA10/MA30)对比':^65}")
    print(f"{'='*65}")
    print(f"{'股票':>8}  {'累计回报':>8}  {'最大回撤':>8}  {'夏普比率':>8}  {'年化收益':>8}  {'年化波动':>8}  {'交易次数':>8}")
    print(f"{'-'*65}")
    
    cross_stock_results = []
    for sname, sdf in [('寒武纪', hw_df), ('宁德时代', stock_data['宁德时代']), ('贵州茅台', stock_data['贵州茅台'])]:
        res = backtest_ma(sdf['close'].values, 10, 30)
        if res is None: continue
        cross_stock_results.append({
            '股票': sname, '参数': 'MA10/30',
            '累计回报': res['cum_return']*100,
            '最大回撤': res['mdd']*100,
            '年化收益': res['ann_return']*100,
            '年化波动': res['ann_vol']*100,
            '夏普比率': res['sharpe'],
            '交易次数': res['n_buy']+res['n_sell']
        })
        print(f"{sname:>8}  {res['cum_return']*100:>7.2f}%  {res['mdd']*100:>7.2f}%  {res['sharpe']:>8.4f}  {res['ann_return']*100:>7.2f}%  {res['ann_vol']*100:>7.2f}%  {res['n_buy']+res['n_sell']:>8}")

# ---------- 可视化1：寒武纪多参数净值对比 ----------
fig, axes = plt.subplots(2, 3, figsize=(18, 10))
axes = axes.flatten()
colors = ['#d62728', '#1f77b4', '#2ca02c', '#ff7f0e', '#9467bd', '#8c564b']

for idx, ((sw, lw), ax) in enumerate(zip(param_sets, axes)):
    res = backtest_ma(hw_close, sw, lw)
    if res is None: continue
    ax.plot(pd.to_datetime(hw_dates), res['equity'], color=colors[idx], linewidth=1.2)
    ax.axhline(y=1.0, color='gray', linestyle='--', linewidth=0.5, alpha=0.5)
    ax.set_title(f'MA{sw}/MA{lw}  Sharpe={res["sharpe"]:.3f}', fontsize=11)
    ax.set_ylabel('净值')
    ax.grid(True, alpha=0.2)
    ax.set_xlim(pd.to_datetime(hw_dates[0]), pd.to_datetime(hw_dates[-1]))

fig.suptitle('寒武纪（688256.SH）不同均线参数策略净值对比', fontsize=14, fontweight='bold')
plt.tight_layout(rect=[0, 0, 1, 0.95])
chart1 = os.path.join(OUT_DIR, 'TASK4_多参数净值对比.png')
fig.savefig(chart1, dpi=300, bbox_inches='tight')
plt.close()
print(f"\n✅ 多参数净值对比图已保存")

# ---------- 可视化2：寒武纪最优参数回测全景 ----------
best_param = max(all_results, key=lambda x: x['夏普比率'])
best_parts = best_param['参数'].replace('MA','').split('/')
best_sw, best_lw = int(best_parts[0]), int(best_parts[1])
best_res = backtest_ma(hw_close, best_sw, best_lw)

fig2 = plt.figure(figsize=(18, 12))
gs = GridSpec(3, 1, figure=fig2, height_ratios=[3, 1.5, 1.5], hspace=0.3)
ax1 = fig2.add_subplot(gs[0])
ax2 = fig2.add_subplot(gs[1])
ax3 = fig2.add_subplot(gs[2])

dates_pd = pd.to_datetime(hw_dates)
ax1.plot(dates_pd, hw_close, color='#333333', linewidth=1.0, label='收盘价', alpha=0.6)
ax1.plot(dates_pd, best_res['ma_short'], color='#d62728', linewidth=1.5, label=f'MA{best_sw}')
ax1.plot(dates_pd, best_res['ma_long'], color='#1f77b4', linewidth=1.5, label=f'MA{best_lw}')
buy_idx = np.where(best_res['signal'] == 1)[0]
sell_idx = np.where(best_res['signal'] == -1)[0]
ax1.scatter(dates_pd[buy_idx], hw_close[buy_idx], color='#d62728', s=100, marker='^', zorder=5, label='买入', edgecolors='black', linewidth=0.5)
ax1.scatter(dates_pd[sell_idx], hw_close[sell_idx], color='#2ca02c', s=100, marker='v', zorder=5, label='卖出', edgecolors='black', linewidth=0.5)
ax1.set_title(f'寒武纪 — 最优参数 MA{best_sw}/MA{best_lw}  (Sharpe={best_res["sharpe"]:.4f})', fontsize=14, fontweight='bold')
ax1.legend(loc='upper left', fontsize=9)
ax1.grid(True, alpha=0.2)

ax2.plot(dates_pd, best_res['equity'], color='#d62728', linewidth=1.5)
ax2.axhline(y=1.0, color='gray', linestyle='--', linewidth=0.5)
ax2.set_title('策略净值曲线', fontsize=14, fontweight='bold')
ax2.grid(True, alpha=0.2)

ax3.fill_between(dates_pd, 0, best_res['drawdown'], color='#2ca02c', alpha=0.4)
ax3.plot(dates_pd, best_res['drawdown'], color='#2ca02c', linewidth=1.0)
ax3.axhline(y=0, color='gray', linewidth=0.5)
ax3.set_title('回撤曲线', fontsize=14, fontweight='bold')
ax3.grid(True, alpha=0.2)

chart2 = os.path.join(OUT_DIR, 'TASK4_最优参数回测全景.png')
fig2.savefig(chart2, dpi=300, bbox_inches='tight')
plt.close()
print(f"✅ 最优参数回测全景图已保存")

# ---------- 导出全部结果 ----------
all_rows = all_results.copy()

result_df = pd.DataFrame(all_rows)
# 格式化输出
result_df['累计回报'] = result_df['累计回报'].apply(lambda x: f'{x:.2f}%')
result_df['最大回撤'] = result_df['最大回撤'].apply(lambda x: f'{x:.2f}%')
result_df['年化收益'] = result_df['年化收益'].apply(lambda x: f'{x:.2f}%')
result_df['年化波动'] = result_df['年化波动'].apply(lambda x: f'{x:.2f}%')
result_df['夏普比率'] = result_df['夏普比率'].apply(lambda x: f'{x:.4f}')
result_csv = os.path.join(OUT_DIR, 'TASK4_多股票多参数回测对比.csv')
result_df.to_csv(result_csv, index=False, encoding='utf-8-sig')
print(f"\n✅ 对比结果已保存至：{result_csv}")
print(f"\n{result_df.to_string(index=False)}")

print(f"\n{'='*65}")
print(f"{'双均线策略试用场景与应用心得总结':^65}")
print(f"{'='*65}")
print("""
1. 参数选择影响显著：同一股票使用不同均线参数，策略表现差异巨大。
   短期参数(MA5/15)信号频繁，但易在震荡市中反复受损；
   长期参数(MA20/60)信号稀少，可能错过关键行情。

2. 股票特性决定策略适配度：
   - 高波动科技股(如寒武纪)：双均线策略容易被剧烈波动打乱节奏，
     金叉死叉频繁交替，累积交易成本。
   - 大盘蓝筹股(如贵州茅台)：波动相对温和，但趋势可能不够明显，
     均线交叉信号间距较长。
   - 成长型股票(如宁德时代)：趋势性较强时策略表现相对较好。

3. 双均线策略最适合有明确单边趋势的市场环境——在趋势行情中，
   金叉和死叉能够有效捕获主要涨跌波段。在横盘震荡或"猴市"中，
   均线频繁交叉产生大量虚假信号，策略表现显著恶化。

4. 改进方向：(1)增加趋势过滤，仅在更大周期均线方向一致时交易；
   (2)增加成交量确认，避免无量突破的假信号；
   (3)针对具体标的的历史数据做参数优化；
   (4)结合波动率指标(如布林带带宽)识别震荡区间，规避震荡行情。
""")
