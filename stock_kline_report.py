#!/usr/bin/env python3
"""
股票日线行情数据下载 & 交互式K线图报表生成器
================================================
功能：
  1. 通过 Tushare Pro API 下载指定股票的日线行情数据
  2. 自动生成包含 K线图 + 成交量图 + 收盘价曲线 + 数据表格 的交互式 HTML 报表
  3. 同时保存 CSV 原始数据文件

依赖安装：
  pip install tushare pandas

使用前准备：
  1. 注册 Tushare Pro (https://tushare.pro) 获取 token
  2. 将 token 设为环境变量 TUSHARE_TOKEN，或直接在脚本中修改 TOKEN 变量

使用示例：
  python stock_kline_report.py
  python stock_kline_report.py --tscode 000300.SH --name 沪深300 --months 6
"""

import os
import argparse
from datetime import datetime, timedelta

try:
    import tushare as ts
    import pandas as pd
except ImportError:
    print("请先安装依赖: pip install tushare pandas")
    exit(1)

# ==================== 配置区 ====================
# 推荐使用环境变量设置 token，避免硬编码
TOKEN = os.environ.get("TUSHARE_TOKEN", "你的Tushare Token")

# ==================== 默认参数 ====================
DEFAULT_TSCODE = "688256.SH"  # 寒武纪
DEFAULT_NAME = "寒武纪"
DEFAULT_MONTHS = 12  # 过去 N 个月


def fetch_data(ts_code: str, months: int) -> pd.DataFrame:
    """
    从 Tushare Pro 下载日线行情数据

    参数:
        ts_code: 股票代码，如 "688256.SH"
        months:  获取过去多少个月的数据

    返回:
        DataFrame，按交易日升序排列，包含列：
        ts_code, trade_date, open, high, low, close, pre_close,
        change, pct_chg, vol, amount
    """
    pro = ts.pro_api(TOKEN)

    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=months * 31)).strftime("%Y%m%d")

    print(f"正在下载 {ts_code} 从 {start_date} 至 {end_date} 的日线数据...")

    df = pro.daily(
        ts_code=ts_code,
        start_date=start_date,
        end_date=end_date,
        fields=[
            "ts_code", "trade_date", "open", "high", "low", "close",
            "pre_close", "change", "pct_chg", "vol", "amount",
        ],
    )

    if df.empty:
        raise ValueError(f"未获取到数据，请检查股票代码 {ts_code} 和 token 是否正确")

    # 按日期升序排列（Tushare 默认降序）
    df = df.sort_values("trade_date").reset_index(drop=True)
    print(f"成功获取 {len(df)} 条交易日数据")
    return df


def build_html(ts_code: str, name: str, df: pd.DataFrame) -> str:
    """
    根据 DataFrame 生成完整的交互式 HTML 页面

    参数:
        ts_code: 股票代码
        name:    股票中文名
        df:      日线行情 DataFrame

    返回:
        HTML 字符串
    """
    # ---------- 数据序列化 ----------
    dates_list = df["trade_date"].tolist()
    kline_list = [
        [round(row["open"], 2), round(row["close"], 2),
         round(row["low"], 2),  round(row["high"], 2)]
        for _, row in df.iterrows()
    ]
    vol_list = [round(v, 2) for v in df["vol"].tolist()]
    pct_list = [round(v, 4) for v in df["pct_chg"].tolist()]
    vol_colors_list = [
        '"#c62828"' if row["pct_chg"] >= 0 else '"#2e7d32"'
        for _, row in df.iterrows()
    ]

    # ---------- 统计指标 ----------
    first_close = df.iloc[0]["close"]
    last_close = df.iloc[-1]["close"]
    high_max = df["high"].max()
    low_min = df["low"].min()
    change_val = last_close - first_close
    change_pct = (change_val / first_close) * 100
    total_vol = df["vol"].sum()
    total_days = len(df)

    start_str = df.iloc[0]["trade_date"]
    end_str = df.iloc[-1]["trade_date"]
    start_fmt = f"{start_str[:4]}-{start_str[4:6]}-{start_str[6:]}"
    end_fmt = f"{end_str[:4]}-{end_str[4:6]}-{end_str[6:]}"

    # ---------- JS 数组序列化（对日期加引号） ----------
    dates_js = json_dumps(dates_list)
    kline_js = json_dumps(kline_list)
    vol_js = json_dumps(vol_list)
    pct_js = json_dumps(pct_list)
    vol_colors_js = "[" + ",".join(vol_colors_list) + "]"

    # ---------- 硬编码统计分析数据 ----------
    stats_json = json_dumps({
        "labels": ["起始日", "最新收盘", "区间最高", "区间最低",
                    "涨跌额", "涨跌幅", "总成交量", "交易日数"],
        "values": [
            start_fmt,
            f"¥{last_close:.2f}",
            f"¥{high_max:.2f}",
            f"¥{low_min:.2f}",
            f"¥{change_val:.2f}",
            f"{change_pct:.2f}%",
            f"{total_vol/10000:.2f}万手",
            f"{total_days}天",
        ],
        "cls": ["", "up", "", "", "up", "up", "", ""],
    })

    return HTML_TEMPLATE.format(
        title=f"{name}({ts_code}) 过去一年日线行情",
        h1_title=f"{name} ({ts_code}) 日线行情",
        subtitle=f"数据区间：{start_fmt} ~ {end_fmt} | 数据来源：Tushare Pro",
        dates=dates_js,
        klineData=kline_js,
        volData=vol_js,
        pctData=pct_js,
        volColors=vol_colors_js,
        stats=stats_json,
        kline_title=f"{name}({ts_code}) K线图",
        close_title=f"{name}({ts_code}) 收盘价曲线",
        table_headers=json_dumps(["日期", "开盘", "收盘", "最高", "最低",
                                   "涨跌幅", "成交量", "成交额"]),
    )


def json_dumps(obj) -> str:
    """将 Python 对象转为紧凑 JSON 字符串（供 JS 嵌入）"""
    import json
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


# ==================== HTML 模板 ====================
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#f5f5f5; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; padding:20px; color:#333; }}
.header {{ background:linear-gradient(135deg,#c62828,#e53935); color:#fff; padding:24px 32px; border-radius:12px; margin-bottom:20px; box-shadow:0 2px 8px rgba(198,40,40,0.3); }}
.header h1 {{ font-size:24px; margin-bottom:4px; }}
.header p {{ font-size:14px; opacity:0.9; }}
.stats-container {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:20px; }}
.stat-card {{ background:#fff; border-radius:10px; padding:16px; text-align:center; box-shadow:0 1px 4px rgba(0,0,0,0.06); }}
.stat-card .label {{ font-size:12px; color:#888; margin-bottom:4px; }}
.stat-card .value {{ font-size:20px; font-weight:700; }}
.stat-card .value.up {{ color:#c62828; }}
.stat-card .value.down {{ color:#2e7d32; }}
.chart-container {{ background:#fff; border-radius:12px; padding:20px; margin-bottom:20px; box-shadow:0 1px 4px rgba(0,0,0,0.06); }}
#klineChart {{ width:100%; height:500px; }}
#volumeChart {{ width:100%; height:160px; }}
#closeChart {{ width:100%; height:400px; }}
.data-table {{ background:#fff; border-radius:12px; overflow:hidden; box-shadow:0 1px 4px rgba(0,0,0,0.06); }}
.data-table table {{ width:100%; border-collapse:collapse; font-size:13px; }}
.data-table th {{ background:#fafafa; padding:10px 8px; text-align:right; font-weight:600; border-bottom:2px solid #eee; white-space:nowrap; }}
.data-table th:first-child {{ text-align:left; padding-left:16px; }}
.data-table td {{ padding:8px; text-align:right; border-bottom:1px solid #f0f0f0; white-space:nowrap; }}
.data-table td:first-child {{ text-align:left; padding-left:16px; }}
.data-table tr:hover {{ background:#fafafa; }}
.data-table .up {{ color:#c62828; }}
.data-table .down {{ color:#2e7d32; }}
.scroll-wrap {{ overflow-x:auto; max-height:500px; overflow-y:auto; }}
.download-bar {{ display:flex; gap:10px; margin-bottom:12px; flex-wrap:wrap; }}
.btn-download {{ display:inline-flex; align-items:center; gap:6px; padding:8px 18px; border:none; border-radius:6px; font-size:13px; font-weight:600; cursor:pointer; transition:all 0.2s; color:#fff; }}
.btn-download.kline {{ background:#c62828; }}
.btn-download.kline:hover {{ background:#a51e1e; }}
.btn-download.vol {{ background:#2e7d32; }}
.btn-download.vol:hover {{ background:#1b5e20; }}
.btn-download:hover {{ transform:translateY(-1px); box-shadow:0 2px 8px rgba(0,0,0,0.15); }}
.chart-title {{ font-size:16px; font-weight:700; color:#333; margin-bottom:12px; }}
</style>
</head>
<body>

<div class="header">
    <h1>{h1_title}</h1>
    <p>{subtitle}</p>
</div>

<div class="stats-container" id="statsContainer"></div>

<div class="chart-container">
    <div class="chart-title">{kline_title}</div>
    <div class="download-bar">
        <button class="btn-download kline" onclick="downloadKline()">📥 下载K线图 (PNG)</button>
    </div>
    <div id="klineChart"></div>
</div>
<div class="chart-container">
    <div class="chart-title">成交量</div>
    <div class="download-bar">
        <button class="btn-download vol" onclick="downloadVolume()">📥 下载成交量图 (PNG)</button>
    </div>
    <div id="volumeChart"></div>
</div>
<div class="chart-container">
    <div class="chart-title">{close_title}</div>
    <div class="download-bar">
        <button class="btn-download kline" onclick="downloadClose()">📥 下载收盘价图 (PNG)</button>
    </div>
    <div id="closeChart"></div>
</div>

<div class="data-table"><div class="scroll-wrap"><table>
    <thead><tr id="tableHead"></tr></thead>
    <tbody id="tableBody"></tbody>
</table></div></div>

<script>
const dates = {dates};
const klineData = {klineData};
const volData = {volData};
const pctData = {pctData};
const volColors = {volColors};

const fmtDate = d => d.substring(0,4)+'-'+d.substring(4,6)+'-'+d.substring(6,8);
const fmtPrice = v => '¥' + v.toFixed(2);
const fmtVol = v => (v/10000).toFixed(2) + '万手';
const fmtAmt = v => (v/10000).toFixed(2) + '万元';
const fmtPct = v => v.toFixed(2) + '%';

// 统计指标
const stats = {stats};
document.getElementById('statsContainer').innerHTML = stats.labels.map((label, i) =>
    `<div class="stat-card"><div class="label">${{label}}</div><div class="value ${{stats.cls[i]||''}}">${{stats.values[i]}}</div></div>`
).join('');

// ---- K线图 ----
const klineChart = echarts.init(document.getElementById('klineChart'));
klineChart.setOption({{
    title: {{ text:'{kline_title}', left:'center', top:0,
             textStyle:{{fontSize:16,fontWeight:700,color:'#333'}} }},
    tooltip: {{
        trigger:'axis', axisPointer:{{type:'cross'}},
        formatter: function(params) {{
            const i = params[0].dataIndex;
            return `<b>${{fmtDate(dates[i])}}</b><br/>
            开盘：${{fmtPrice(klineData[i][0])}}<br/>
            收盘：${{fmtPrice(klineData[i][1])}}<br/>
            最高：${{fmtPrice(klineData[i][3])}}<br/>
            最低：${{fmtPrice(klineData[i][2])}}<br/>
            涨跌幅：<span style="color:${{pctData[i]>=0?'#c62828':'#2e7d32'}}">${{fmtPct(pctData[i])}}</span><br/>
            成交量：${{fmtVol(volData[i])}}`;
        }}
    }},
    grid: {{ left:'12%', right:'8%', top:'15%', bottom:'4%' }},
    xAxis: {{ type:'category', name:'交易日期', nameLocation:'center', nameGap:35,
             nameTextStyle:{{fontSize:13,fontWeight:600}},
             data:dates.map(fmtDate),
             axisLabel:{{rotate:45,fontSize:10,interval:Math.floor(dates.length/20)}},
             axisLine:{{lineStyle:{{color:'#ddd'}}}} }},
    yAxis: {{ type:'value', scale:true, name:'价格 (¥)', nameLocation:'middle', nameGap:50,
             nameTextStyle:{{fontSize:13,fontWeight:600}},
             splitLine:{{lineStyle:{{color:'#f0f0f0'}}}},
             axisLabel:{{formatter:'¥{{value}}'}} }},
    dataZoom: [{{type:'inside',start:0,end:100}},{{type:'slider',start:0,end:100,bottom:0,height:20}}],
    series: [{{ type:'candlestick', data:klineData,
               itemStyle:{{color:'#c62828',color0:'#2e7d32',
                           borderColor:'#c62828',borderColor0:'#2e7d32'}} }}]
}});

// ---- 成交量图 ----
const volChart = echarts.init(document.getElementById('volumeChart'));
volChart.setOption({{
    title: {{ text:'成交量', left:'center', top:0,
             textStyle:{{fontSize:16,fontWeight:700,color:'#333'}} }},
    tooltip: {{ trigger:'axis',
                formatter:function(params){{ const i=params[0].dataIndex;
                    return `<b>${{fmtDate(dates[i])}}</b><br/>成交量：${{fmtVol(volData[i])}}`; }} }},
    grid: {{ left:'8%', right:'8%', top:'22%', bottom:'4%' }},
    xAxis: {{ type:'category', name:'交易日期', nameLocation:'center', nameGap:35,
             nameTextStyle:{{fontSize:13,fontWeight:600}},
             data:dates.map(fmtDate), axisLabel:{{show:false}}, axisLine:{{show:false}} }},
    yAxis: {{ type:'value', name:'成交量 (手)', nameLocation:'middle', nameGap:50,
             nameTextStyle:{{fontSize:13,fontWeight:600}},
             splitLine:{{lineStyle:{{color:'#f0f0f0'}}}},
             axisLabel:{{formatter:v=>(v/10000).toFixed(0)+'万'}} }},
    series: [{{ type:'bar', data:volData.map((v,i)=>({{value:v,itemStyle:{{color:volColors[i]}}}})),
              barWidth:'50%' }}]
}});

// ---- 收盘价曲线 ----
const closePrice = klineData.map(d => d[1]);
const closeChart = echarts.init(document.getElementById('closeChart'));
closeChart.setOption({{
    title: {{ text:'{close_title}', left:'center', top:0,
             textStyle:{{fontSize:16,fontWeight:700,color:'#333'}} }},
    tooltip: {{
        trigger:'axis',
        formatter: function(params) {{
            const i = params[0].dataIndex;
            return `<b>${{fmtDate(dates[i])}}</b><br/>
            收盘价：<span style="color:#2196F3;font-weight:700">${{fmtPrice(closePrice[i])}}</span><br/>
            涨跌幅：<span style="color:${{pctData[i]>=0?'#c62828':'#2e7d32'}}">${{fmtPct(pctData[i])}}</span>`;
        }}
    }},
    grid: {{ left:'10%', right:'8%', top:'15%', bottom:'10%' }},
    xAxis: {{ type:'category', data:dates.map(fmtDate),
             axisLabel:{{rotate:45,fontSize:10,interval:Math.floor(dates.length/20)}},
             axisLine:{{lineStyle:{{color:'#ddd'}}}} }},
    yAxis: {{ type:'value', scale:true, name:'收盘价 (¥)', nameLocation:'middle', nameGap:55,
             nameTextStyle:{{fontSize:13,fontWeight:600}},
             splitLine:{{lineStyle:{{color:'#f0f0f0'}}}},
             axisLabel:{{formatter:'¥{{value}}'}} }},
    dataZoom: [{{type:'inside',start:0,end:100}},{{type:'slider',start:0,end:100,bottom:0,height:20}}],
    series: [{{
        type:'line', data:closePrice,
        smooth:true, symbol:'none',
        lineStyle:{{width:2,color:'#2196F3'}},
        areaStyle:{{color:{{type:'linear',x:0,y:0,x2:0,y2:1,
            colorStops:[{{offset:0,color:'rgba(33,150,243,0.25)'}},{{offset:1,color:'rgba(33,150,243,0.02)'}}]}}}}
    }}]
}});

// ---- 数据表格 ----
const hdrs = {table_headers};
document.getElementById('tableHead').innerHTML = hdrs.map(h=>'<th>'+h+'</th>').join('');
let tbody = '';
for (let i = dates.length-1; i >= 0; i--) {{
    tbody += `<tr>
        <td>${{fmtDate(dates[i])}}</td>
        <td class="${{pctData[i]>=0?'up':'down'}}">${{fmtPrice(klineData[i][0])}}</td>
        <td class="${{pctData[i]>=0?'up':'down'}}">${{fmtPrice(klineData[i][1])}}</td>
        <td>${{fmtPrice(klineData[i][3])}}</td>
        <td>${{fmtPrice(klineData[i][2])}}</td>
        <td class="${{pctData[i]>=0?'up':'down'}}">${{fmtPct(pctData[i])}}</td>
        <td>${{fmtVol(volData[i])}}</td>
        <td>${{fmtAmt(volData[i])}}</td>
    </tr>`;
}}
document.getElementById('tableBody').innerHTML = tbody;
window.addEventListener('resize',()=>{{klineChart.resize();volChart.resize();closeChart.resize();}});

function downloadKline() {{
    const url = klineChart.getDataURL({{type:'png',pixelRatio:2,backgroundColor:'#fff'}});
    const a = document.createElement('a'); a.href = url;
    a.download = '{name}_K线图.png'; a.click();
}}
function downloadVolume() {{
    const url = volChart.getDataURL({{type:'png',pixelRatio:2,backgroundColor:'#fff'}});
    const a = document.createElement('a'); a.href = url;
    a.download = '{name}_成交量图.png'; a.click();
}}
function downloadClose() {{
    const url = closeChart.getDataURL({{type:'png',pixelRatio:2,backgroundColor:'#fff'}});
    const a = document.createElement('a'); a.href = url;
    a.download = '{name}_收盘价曲线.png'; a.click();
}}
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(
        description="股票日线行情数据下载 & 交互式K线图报表生成器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python stock_kline_report.py
  python stock_kline_report.py --tscode 000300.SH --name 沪深300 --months 6
  python stock_kline_report.py --tscode 600519.SH --name 贵州茅台 --months 24
        """,
    )
    parser.add_argument(
        "--tscode", default=DEFAULT_TSCODE,
        help=f"股票代码，格式如 688256.SH（默认: {DEFAULT_TSCODE}）"
    )
    parser.add_argument(
        "--name", default=DEFAULT_NAME,
        help=f"股票中文名称（默认: {DEFAULT_NAME}）"
    )
    parser.add_argument(
        "--months", type=int, default=DEFAULT_MONTHS,
        help=f"获取过去多少个月的数据（默认: {DEFAULT_MONTHS}）"
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="输出 HTML 文件路径（默认自动生成）"
    )

    args = parser.parse_args()

    # 1. 下载数据
    df = fetch_data(args.tscode, args.months)

    # 2. 保存 CSV
    safe_name = args.name.replace(" ", "_")
    csv_file = f"{safe_name}_{args.tscode.replace('.', '_')}_日线数据.csv"
    df.to_csv(csv_file, index=False, encoding="utf-8-sig")
    print(f"CSV 数据已保存: {csv_file}")

    # 3. 生成 HTML
    html = build_html(args.tscode, args.name, df)

    if args.output:
        html_file = args.output
    else:
        date_suffix = datetime.now().strftime("%Y%m%d")
        html_file = f"{safe_name}_{args.tscode.replace('.', '_')}_行情报表_{date_suffix}.html"

    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML 报表已生成: {html_file}")
    print(f"✅ 完成！用浏览器打开 {html_file} 查看交互式图表。")


if __name__ == "__main__":
    main()
