# 量化交易：AI大模型辅助的金融交易策略

基于 Tushare Pro 数据的 A 股量化分析全流程实战项目。

## 项目路线图

| Task | 主题 | 内容 |
|------|------|------|
| **Task 1** | 基础行情数据 | 日线数据获取、K线图看板、CSV 导出 |
| **Task 2** | 数据诊断与技术指标 | 数据质量分析、MA/MACD/RSI/布林带/KDJ 指标 |
| **Task 3** | 双均线策略回测 | 金叉死叉策略、多股票多参数对比、最优参数搜索 |
| **Task 4** | 海龟交易法则 | 唐奇安通道、ATR 仓位管理、多品种回测 |

## 成果门户

👉 [打开成果门户](index.html) — 一站式浏览所有看板、图表和数据

## 技术栈

- **数据源**: Tushare Pro
- **数据处理**: Python, Pandas, NumPy
- **可视化**: ECharts, Chart.js, Matplotlib
- **策略回测**: 双均线策略、海龟交易法则

## 快速开始

```bash
pip install tushare pandas
# 设置 TUSHARE_TOKEN 环境变量后运行:
python "Task 1/stock_kline_report.py"
```

## 开源协议

MIT
