"""生成回测指标对比柱状图"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import os

# 中文字体
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

models = ['Ridge 回归', '决策树回归', '随机森林回归', 'GBDT', '沪深300基准']
colors = ['#e74c3c', '#f39c12', '#3498db', '#2ecc71', '#95a5a6']

# 数据（从CSV读取）
cum_ret   = [20.58, 8.19, 16.75, 19.51, 11.77]
ann_ret   = [28.34, 11.07, 22.93, 26.82, 16.00]
sharpe    = [0.9042, 0.3588, 0.7731, 0.9720, 0.6058]
mdd       = [1.39, 5.30, 2.66, 1.54, 2.85]  # 取绝对值

fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle('四类回归模型回测核心指标对比', fontsize=16, fontweight='bold', y=0.98)

# 累计收益
ax = axes[0, 0]
bars = ax.bar(models, cum_ret, color=colors, edgecolor='white', width=0.6)
ax.set_title('累计收益 (%)', fontsize=13, fontweight='bold')
ax.set_ylabel('累计收益 (%)')
for bar, val in zip(bars, cum_ret):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3, f'{val}%', ha='center', va='bottom', fontsize=10)
ax.axhline(y=cum_ret[-1], color='#95a5a6', linestyle='--', linewidth=1, alpha=0.7, label='基准线')
ax.legend(fontsize=9)
ax.tick_params(axis='x', labelsize=9)

# 年化收益
ax = axes[0, 1]
bars = ax.bar(models, ann_ret, color=colors, edgecolor='white', width=0.6)
ax.set_title('年化收益 (%)', fontsize=13, fontweight='bold')
ax.set_ylabel('年化收益 (%)')
for bar, val in zip(bars, ann_ret):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3, f'{val}%', ha='center', va='bottom', fontsize=10)
ax.axhline(y=ann_ret[-1], color='#95a5a6', linestyle='--', linewidth=1, alpha=0.7, label='基准线')
ax.legend(fontsize=9)
ax.tick_params(axis='x', labelsize=9)

# 夏普比率
ax = axes[1, 0]
bars = ax.bar(models, sharpe, color=colors, edgecolor='white', width=0.6)
ax.set_title('夏普比率', fontsize=13, fontweight='bold')
ax.set_ylabel('夏普比率')
for bar, val in zip(bars, sharpe):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01, f'{val}', ha='center', va='bottom', fontsize=10)
ax.axhline(y=sharpe[-1], color='#95a5a6', linestyle='--', linewidth=1, alpha=0.7, label='基准线')
ax.legend(fontsize=9)
ax.tick_params(axis='x', labelsize=9)

# 最大回撤
ax = axes[1, 1]
bars = ax.bar(models, mdd, color=colors, edgecolor='white', width=0.6)
ax.set_title('最大回撤 (%, 绝对值)', fontsize=13, fontweight='bold')
ax.set_ylabel('最大回撤 (%)')
for bar, val in zip(bars, mdd):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05, f'-{val}%', ha='center', va='bottom', fontsize=10)
ax.axhline(y=mdd[-1], color='#95a5a6', linestyle='--', linewidth=1, alpha=0.7, label='基准线')
ax.legend(fontsize=9)
ax.tick_params(axis='x', labelsize=9)

plt.tight_layout(rect=[0, 0, 1, 0.95])
out_path = os.path.join(OUT_DIR, 'TASK6_回测指标对比图.png')
plt.savefig(out_path, dpi=180, bbox_inches='tight', facecolor='white')
plt.close()
print(f'已保存: {out_path}')
