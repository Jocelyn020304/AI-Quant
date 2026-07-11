"""保存宁德时代和茅台数据到CSV，并运行三股对比分析"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os, json

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

OUT_DIR = r'C:\Users\Administrator\Desktop\量化交易：AI大模型辅助的金融交易策略\Task 3'

# 从MCP返回的JSON构建DataFrame
ndsd_json = r'C:\Users\Administrator\.workbuddy\projects\c-Users-Administrator-Desktop-量化交易：AI大模型辅助的金融交易策略-Task 3\d7ecfebc-dada-4e4a-87ed-41f873d2f178\tool-results\call_00_sT4CuLPkxJuK3B1lNRQt3023.txt'
mt_json = r'C:\Users\Administrator\.workbuddy\projects\c-Users-Administrator-Desktop-量化交易：AI大模型辅助的金融交易策略-Task 3\d7ecfebc-dada-4e4a-87ed-41f873d2f178\tool-results\call_00_Zi1TKSpUa3zgNGRP7MoK8976.txt'

# 尝试从MCP返回文本加载JSON数据
try:
    with open(ndsd_json, 'r', encoding='utf-8') as f:
        ndsd_data = json.loads(f.read())
    ndsd_df = pd.DataFrame(ndsd_data)
    ndsd_df['trade_date'] = pd.to_datetime(ndsd_df['trade_date'], format='%Y%m%d')
    ndsd_df = ndsd_df.sort_values('trade_date').reset_index(drop=True)
    ndsd_df.to_csv(os.path.join(OUT_DIR, 'stock_data', '宁德时代_日线数据.csv'), index=False, encoding='utf-8-sig')
    print(f'✅ 宁德时代: {len(ndsd_df)}行 -> CSV')
except Exception as e:
    print(f'⚠️ 宁德时代加载失败: {e}')
    ndsd_df = None

try:
    with open(mt_json, 'r', encoding='utf-8') as f:
        mt_data = json.loads(f.read())
    mt_df = pd.DataFrame(mt_data)
    mt_df['trade_date'] = pd.to_datetime(mt_df['trade_date'], format='%Y%m%d')
    mt_df = mt_df.sort_values('trade_date').reset_index(drop=True)
    mt_df.to_csv(os.path.join(OUT_DIR, 'stock_data', '贵州茅台_日线数据.csv'), index=False, encoding='utf-8-sig')
    print(f'✅ 贵州茅台: {len(mt_df)}行 -> CSV')
except Exception as e:
    print(f'⚠️ 贵州茅台加载失败: {e}')
    mt_df = None

# 加载寒武纪
hw_path = r'C:\Users\Administrator\Desktop\量化交易：AI大模型辅助的金融交易策略\Task 1\寒武纪_过去一年日线数据.csv'
hw_df = pd.read_csv(hw_path, encoding='utf-8-sig')
hw_df['trade_date'] = pd.to_datetime(hw_df['trade_date'], format='%Y%m%d')
hw_df = hw_df.sort_values('trade_date').reset_index(drop=True)

# 合并成字典
stocks = {'寒武纪': hw_df}
if ndsd_df is not None:
    stocks['宁德时代'] = ndsd_df
if mt_df is not None:
    stocks['贵州茅台'] = mt_df

print(f'\n三只股票数据就绪: {", ".join(stocks.keys())}')

# 回测函数
def backtest(close, sw, lw):
    n = len(close)
    s = pd.Series(close)
    ma_s = s.rolling(sw).mean().values
    ma_l = s.rolling(lw).mean().values
    sig = np.zeros(n, dtype=int)
    for i in range(1, n):
        if np.isnan(ma_s[i]) or np.isnan(ma_l[i]): continue
        if np.isnan(ma_s[i-1]) or np.isnan(ma_l[i-1]): continue
        if ma_s[i-1] <= ma_l[i-1] and ma_s[i] > ma_l[i]: sig[i] = 1
        elif ma_s[i-1] >= ma_l[i-1] and ma_s[i] < ma_l[i]: sig[i] = -1
    pos = 0; eq = np.ones(n); entry = 0
    for i in range(1, n):
        if sig[i] == 1 and pos == 0: pos = 1; entry = i
        elif sig[i] == -1 and pos == 1: pos = 0; eq[i:] = eq[i:] * (close[i] / close[entry])
    if pos == 1: eq[-1] = eq[-1] * (close[-1] / close[entry])
    ret = eq[-1] - 1.0
    dd = np.min((eq - np.maximum.accumulate(eq)) / np.maximum.accumulate(eq))
    dr = np.diff(eq) / eq[:-1]
    ar = np.mean(dr) * 252 if len(dr) > 0 else 0
    av = np.std(dr, ddof=1) * np.sqrt(252) if len(dr) > 1 else 0
    sr = (ar - 0.02) / av if av > 0 else 0
    return ret, dd, sr, ar, av, int(np.sum(sig != 0)), eq

# MA10/30 三股对比
params = (10, 30)
print(f'\n{"="*70}')
print(f'{"三只股票相同参数(MA10/MA30)回测对比":^70}')
print(f'{"="*70}')
print(f'{"股票":>10} {"代码":>12} {"累计回报":>10} {"最大回撤":>10} {"夏普比率":>10} {"年化收益":>10} {"信号次数":>8}')
print("-"*70)

comp = []
for sname, sdf in stocks.items():
    c = sdf['close'].values
    ret, dd, sr, ar, av, nt, eq = backtest(c, *params)
    code = sdf['ts_code'].iloc[0] if 'ts_code' in sdf.columns else '-'
    comp.append((sname, code, ret, dd, sr, ar, av, nt, eq, sdf['trade_date']))
    print(f"{sname:>10} {code:>12} {ret*100:>8.2f}% {dd*100:>8.2f}% {sr:>10.4f} {ar*100:>8.2f}% {nt:>8}")

# 三股净值对比图
fig, ax = plt.subplots(figsize=(16, 8))
colors = {'寒武纪': '#d62728', '宁德时代': '#1f77b4', '贵州茅台': '#2ca02c'}
for sname, code, ret, dd, sr, ar, av, nt, eq, dates in comp:
    ax.plot(dates, eq, color=colors.get(sname, '#333'), linewidth=1.8, label=f'{sname} ({code})  Sharpe={sr:.3f}')
ax.axhline(y=1.0, color='gray', linestyle='--', linewidth=0.8, alpha=0.5)
ax.set_title(f'双均线策略(MA{params[0]}/MA{params[1]}) 三只股票净值对比', fontsize=14, fontweight='bold')
ax.set_ylabel('策略净值')
ax.legend(loc='best', fontsize=11)
ax.grid(True, alpha=0.2)
fig.tight_layout()
chart_path = os.path.join(OUT_DIR, 'TASK4_三股净值对比.png')
fig.savefig(chart_path, dpi=300, bbox_inches='tight')
plt.close()
print(f'\n✅ 三股净值对比图已保存')

# 输出对比表
rows = []
for sname, code, ret, dd, sr, ar, av, nt, eq, _ in comp:
    rows.append({'股票': sname, '代码': code, '参数': f'MA{params[0]}/{params[1]}',
                 '累计回报': f'{ret*100:.2f}%', '最大回撤': f'{dd*100:.2f}%',
                 '夏普比率': f'{sr:.4f}', '年化收益': f'{ar*100:.2f}%',
                 '年化波动': f'{av*100:.2f}%', '交易次数': nt})
rdf = pd.DataFrame(rows)
csv_path = os.path.join(OUT_DIR, 'TASK4_三股对比.csv')
rdf.to_csv(csv_path, index=False, encoding='utf-8-sig')
print(f'✅ 对比表已保存')
print(f'\n{rdf.to_string(index=False)}')
