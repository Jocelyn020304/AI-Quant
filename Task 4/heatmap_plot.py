"""
生成海龟策略多参数对比热力图：累计回报 + 夏普比率
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import os
from matplotlib.colors import LinearSegmentedColormap

matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
matplotlib.rcParams['axes.unicode_minus'] = False

OUT_DIR = r'C:\Users\Administrator\Desktop\量化交易：AI大模型辅助的金融交易策略\Task 4'
CSV_PATH = os.path.join(OUT_DIR, 'TASK4_多股票多参数回测对比.csv')

df = pd.read_csv(CSV_PATH, encoding='utf-8-sig')

# 整理数据为矩阵格式
stocks = list(df['股票'].unique())
periods = list(df['通道周期'].unique())

def to_float(val):
    if isinstance(val, str) and '%' in val:
        return float(val.strip('%')) / 100
    return float(val)

# 累计回报矩阵
cumu_matrix = np.zeros((len(stocks), len(periods)))
sharpe_matrix = np.zeros((len(stocks), len(periods)))

for i, stock in enumerate(stocks):
    sub = df[df['股票'] == stock]
    for j, p in enumerate(periods):
        row = sub[sub['通道周期'] == p].iloc[0]
        cumu_matrix[i, j] = to_float(row['累计回报'])
        sharpe_matrix[i, j] = float(row['夏普比率'])

# 创建自定义色图：绿(亏损) → 白(零) → 红(盈利)
colors_cumu = [(0.0, 0.6, 0.2),   # 深绿（大幅亏损）
               (0.6, 0.85, 0.6),  # 浅绿
               (1.0, 1.0, 1.0),   # 白色（零轴）
               (1.0, 0.85, 0.6),  # 浅红
               (0.8, 0.1, 0.1)]   # 深红（大幅盈利）
cmap_cumu = LinearSegmentedColormap.from_list('profit_loss', colors_cumu, N=256)

colors_sharpe = [(0.3, 0.3, 0.8),  # 深蓝（负值）
                 (0.7, 0.7, 1.0),
                 (1.0, 1.0, 1.0),  # 白色（零）
                 (1.0, 0.8, 0.5),
                 (0.8, 0.3, 0.0)]  # 橙红（正值）
cmap_sharpe = LinearSegmentedColormap.from_list('sharpe_scale', colors_sharpe, N=256)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))

# ===== 热力图1：累计回报 =====
vmin_c = min(cumu_matrix.min(), -0.05)
vmax_c = max(cumu_matrix.max(), 0.05)
# 以0为对称中心
vlim = max(abs(vmin_c), abs(vmax_c))
im1 = ax1.imshow(cumu_matrix, cmap=cmap_cumu, aspect='auto', vmin=-vlim, vmax=vlim)

# 填充数值
for i in range(len(stocks)):
    for j in range(len(periods)):
        val = cumu_matrix[i, j]
        color = 'white' if abs(val) > 0.12 else 'black'
        ax1.text(j, i, f'{val:.1%}', ha='center', va='center', fontsize=11,
                 fontweight='bold', color=color)

ax1.set_xticks(range(len(periods)))
ax1.set_xticklabels([f'{p}日' for p in periods], fontsize=11)
ax1.set_yticks(range(len(stocks)))
ax1.set_yticklabels([s.split('（')[0] for s in stocks], fontsize=11)
ax1.set_title('累计回报热力图', fontsize=14, fontweight='bold', pad=12)

# 添加色标
cbar1 = fig.colorbar(im1, ax=ax1, shrink=0.85, pad=0.02)
cbar1.set_label('累计回报', fontsize=10)

# 标记最佳值
best_idx = np.unravel_index(np.argmax(cumu_matrix), cumu_matrix.shape)
ax1.add_patch(plt.Rectangle((best_idx[1]-0.5, best_idx[0]-0.5), 1, 1,
                             fill=False, edgecolor='gold', linewidth=3, linestyle='-'))

# ===== 热力图2：夏普比率 =====
vmin_s = min(sharpe_matrix.min(), -0.5)
vmax_s = max(sharpe_matrix.max(), 0.5)
vlim_s = max(abs(vmin_s), abs(vmax_s), 1.0)
im2 = ax2.imshow(sharpe_matrix, cmap=cmap_sharpe, aspect='auto', vmin=-vlim_s, vmax=vlim_s)

for i in range(len(stocks)):
    for j in range(len(periods)):
        val = sharpe_matrix[i, j]
        color = 'white' if abs(val) > 1.2 else 'black'
        ax2.text(j, i, f'{val:.2f}', ha='center', va='center', fontsize=11,
                 fontweight='bold', color=color)

ax2.set_xticks(range(len(periods)))
ax2.set_xticklabels([f'{p}日' for p in periods], fontsize=11)
ax2.set_yticks(range(len(stocks)))
ax2.set_yticklabels([s.split('（')[0] for s in stocks], fontsize=11)
ax2.set_title('夏普比率热力图', fontsize=14, fontweight='bold', pad=12)

cbar2 = fig.colorbar(im2, ax=ax2, shrink=0.85, pad=0.02)
cbar2.set_label('夏普比率', fontsize=10)

best_idx_s = np.unravel_index(np.argmax(sharpe_matrix), sharpe_matrix.shape)
ax2.add_patch(plt.Rectangle((best_idx_s[1]-0.5, best_idx_s[0]-0.5), 1, 1,
                             fill=False, edgecolor='gold', linewidth=3, linestyle='-'))

plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, 'TASK4_参数对比热力图.png'), dpi=300, bbox_inches='tight')
plt.close()
print("热力图已保存至：TASK4_参数对比热力图.png")
