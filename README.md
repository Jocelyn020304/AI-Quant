# Stock K-Line Report Generator

股票日线行情数据下载与交互式 K 线图报表生成工具。

## 功能

- 通过 [Tushare Pro](https://tushare.pro) 下载指定股票的日线行情数据
- 自动生成交互式 HTML 报表，包含：
  - **K 线图** — 带滑动缩放、十字光标提示
  - **成交量柱状图** — 涨跌着色（A 股红涨绿跌）
  - **收盘价曲线图** — 带渐变面积的平滑折线
  - **关键统计卡片** — 区间最高/最低/涨跌幅/总成交量
  - **完整数据表格** — 按日期倒序，支持横向滚动
  - **一键下载** — 每个图表均可导出为 PNG 图片
- 同时导出 CSV 原始数据

## 快速开始

### 1. 安装依赖

```bash
pip install tushare pandas
```

### 2. 设置 Tushare Token

注册 [Tushare Pro](https://tushare.pro) 获取 token，然后：

```bash
# Linux / macOS
export TUSHARE_TOKEN=你的token

# Windows CMD
set TUSHARE_TOKEN=你的token

# Windows PowerShell
$env:TUSHARE_TOKEN="你的token"
```

也可直接在脚本中修改 `TOKEN` 变量。

### 3. 运行

```bash
# 默认：寒武纪(688256.SH) 过去12个月
python stock_kline_report.py

# 自定义：贵州茅台 过去2年
python stock_kline_report.py --tscode 600519.SH --name 贵州茅台 --months 24

# 指定输出文件
python stock_kline_report.py --tscode 000300.SH --name 沪深300 -o 沪深300行情.html
```

### 4. 查看结果

用浏览器打开生成的 `.html` 文件即可查看交互式图表。

## 输出文件

| 文件 | 说明 |
|------|------|
| `*_行情报表_*.html` | 交互式 HTML 报表（可直接浏览器打开） |
| `*_日线数据.csv` | 原始日线行情数据（UTF-8 with BOM） |

## 技术栈

- **数据源**: Tushare Pro API
- **数据清洗**: Pandas
- **可视化**: ECharts 5
- **颜色规范**: A 股市场红涨绿跌

## 开源协议

[MIT License](LICENSE)
