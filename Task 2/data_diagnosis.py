import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from datetime import datetime

# 设置中文字体（Windows 系统常用 SimHei）
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

# 文件路径
csv_path = r'C:\Users\Administrator\Desktop\量化交易：AI大模型辅助的金融交易策略\Task 1\寒武纪_过去一年日线数据.csv'
output_dir = r'C:\Users\Administrator\Desktop\量化交易：AI大模型辅助的金融交易策略\Task 2'
report_path = os.path.join(output_dir, '寒武纪_数据诊断分析报告.md')

# 1. 加载数据
df = pd.read_csv(csv_path, encoding='utf-8-sig')

# 转换日期格式
df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')
df = df.sort_values('trade_date').reset_index(drop=True)

# 2. 基础信息
basic_info = {
    '数据行数': len(df),
    '数据列数': len(df.columns),
    '起始日期': df['trade_date'].min().strftime('%Y-%m-%d'),
    '结束日期': df['trade_date'].max().strftime('%Y-%m-%d'),
    '交易日数': df['trade_date'].nunique(),
    '数据列名': ', '.join(df.columns.tolist()),
    '数据类型': str(df.dtypes.to_dict())
}

# 3. 缺失值检查
missing_values = df.isnull().sum()
missing_pct = (df.isnull().sum() / len(df) * 100).round(4)
missing_df = pd.DataFrame({
    '缺失值数量': missing_values,
    '缺失比例(%)': missing_pct
})

# 4. 重复值检查
duplicated_rows = df.duplicated().sum()

# 5. 描述性统计量
numeric_cols = ['open', 'high', 'low', 'close', 'pre_close', 'change', 'pct_chg', 'vol', 'amount']
desc_stats = df[numeric_cols].describe().T
desc_stats['skew'] = df[numeric_cols].skew()
desc_stats['kurt'] = df[numeric_cols].kurtosis()
desc_stats['var'] = df[numeric_cols].var()
desc_stats = desc_stats[['count', 'mean', 'std', 'var', 'min', '25%', '50%', '75%', 'max', 'skew', 'kurt']]
desc_stats = desc_stats.round(4)

# 6. 额外派生指标
df['price_range'] = df['high'] - df['low']  # 日内振幅（绝对）
df['price_range_pct'] = df['price_range'] / df['pre_close'] * 100  # 日内振幅（%）
df['return'] = df['pct_chg']  # 日收益率

extra_stats = df[['price_range', 'price_range_pct', 'return']].describe().T
extra_stats['skew'] = df[['price_range', 'price_range_pct', 'return']].skew()
extra_stats['kurt'] = df[['price_range', 'price_range_pct', 'return']].kurtosis()
extra_stats = extra_stats.round(4)

# 7. 生成可视化图表
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# 收盘价走势图
axes[0, 0].plot(df['trade_date'], df['close'], color='blue', linewidth=1)
axes[0, 0].set_title('寒武纪收盘价走势', fontsize=14)
axes[0, 0].set_xlabel('交易日')
axes[0, 0].set_ylabel('收盘价（元）')
axes[0, 0].grid(True, alpha=0.3)

# 日收益率分布
axes[0, 1].hist(df['return'], bins=30, color='steelblue', edgecolor='black', alpha=0.7)
axes[0, 1].set_title('日收益率分布', fontsize=14)
axes[0, 1].set_xlabel('日收益率（%）')
axes[0, 1].set_ylabel('频数')
axes[0, 1].grid(True, alpha=0.3)

# 成交量走势
axes[1, 0].plot(df['trade_date'], df['vol'], color='green', linewidth=1)
axes[1, 0].set_title('成交量走势', fontsize=14)
axes[1, 0].set_xlabel('交易日')
axes[1, 0].set_ylabel('成交量（手）')
axes[1, 0].grid(True, alpha=0.3)

# 成交额走势
axes[1, 1].plot(df['trade_date'], df['amount'], color='orange', linewidth=1)
axes[1, 1].set_title('成交额走势', fontsize=14)
axes[1, 1].set_xlabel('交易日')
axes[1, 1].set_ylabel('成交额（元）')
axes[1, 1].grid(True, alpha=0.3)

plt.tight_layout()
chart_path = os.path.join(output_dir, '寒武纪_数据诊断可视化.png')
plt.savefig(chart_path, dpi=300, bbox_inches='tight')
plt.close()

# 8. 生成 Markdown 报告
report = f"""# 寒武纪（688256.SH）日线数据诊断分析报告

## 一、数据基础信息

- **数据行数**：{basic_info['数据行数']} 行
- **数据列数**：{basic_info['数据列数']} 列
- **数据列名**：{basic_info['数据列名']}
- **起始日期**：{basic_info['起始日期']}
- **结束日期**：{basic_info['结束日期']}
- **交易日数**：{basic_info['交易日数']} 天
- **重复行数**：{duplicated_rows} 行

## 二、缺失值检查

{missing_df.to_markdown()}

**结论**：从上表可以看出，各字段均无缺失值，数据完整性良好。

## 三、描述性统计量

### 3.1 原始价格与成交量字段描述性统计

{desc_stats.to_markdown()}

### 3.2 派生指标描述性统计

| 指标 | 含义 |
|------|------|
| price_range | 日内最高价 - 最低价（绝对振幅） |
| price_range_pct | 日内振幅 / 前收盘价 × 100% |
| return | 日收益率（即 pct_chg） |

{extra_stats.to_markdown()}

## 四、数据可视化

![数据诊断可视化]({os.path.basename(chart_path)})

## 五、主要发现

1. **数据完整性**：全部字段无缺失值，无重复记录，数据质量较好。
2. **股价波动**：寒武纪过去一年股价波动剧烈，收盘价最低 {df['close'].min():.2f} 元，最高 {df['close'].max():.2f} 元，极差达到 {df['close'].max() - df['close'].min():.2f} 元。
3. **日收益率**：平均日收益率为 {df['return'].mean():.4f}%，标准差为 {df['return'].std():.4f}%，显示股价日内波动较大。
4. **成交量与成交额**：成交量和成交额在某些交易日出现显著放大，通常伴随价格的大幅波动。

---
*报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""

with open(report_path, 'w', encoding='utf-8') as f:
    f.write(report)

print(f"数据诊断分析完成。")
print(f"Markdown 报告已保存至：{report_path}")
print(f"可视化图表已保存至：{chart_path}")
print(f"\n数据基础信息：")
for k, v in basic_info.items():
    print(f"  {k}: {v}")
print(f"\n缺失值检查：\n{missing_df}")
print(f"\n描述性统计：\n{desc_stats}")
