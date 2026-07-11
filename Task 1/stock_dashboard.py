#!/usr/bin/env python3
"""
股票行情看板 — 交互式 Web 应用
================================
支持任意 A 股/港股/美股股票，输入代码即可查看 K 线图、成交量、收盘价曲线。

用法：
  1. 设置 TUSHARE_TOKEN 环境变量（或在下方修改 TOKEN 变量）
  2. python stock_dashboard.py
  3. 浏览器打开 http://localhost:5000
"""

import os
import json
from datetime import datetime, timedelta

import tushare as ts
import pandas as pd
from flask import Flask, render_template_string, request, jsonify

# ===== 配置 =====
TOKEN = os.environ.get("TUSHARE_TOKEN", "6f9eca8f7a38eda0bdd0ebbd1c9063498b26a7ee96c374eaba4167eb")
ts.set_token(TOKEN)
pro = ts.pro_api()

# ===== Flask =====
app = Flask(__name__)


def fetch_kline(ts_code: str, months: int = 12) -> pd.DataFrame:
    """从 Tushare 下载日线数据"""
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=months * 31)).strftime("%Y%m%d")
    df = pro.daily(
        ts_code=ts_code, start_date=start, end_date=end,
        fields=["ts_code", "trade_date", "open", "high", "low", "close",
                "pre_close", "change", "pct_chg", "vol", "amount"],
    )
    if df.empty:
        raise ValueError(f"未获取到数据，请检查股票代码: {ts_code}")
    df = df.sort_values("trade_date").reset_index(drop=True)
    return df


def build_data_json(df: pd.DataFrame) -> dict:
    """将 DataFrame 转为前端需要的 JSON 结构"""
    dates = df["trade_date"].tolist()
    kline = [[round(r["open"], 2), round(r["close"], 2),
              round(r["low"], 2), round(r["high"], 2)]
             for _, r in df.iterrows()]
    vol = [round(v, 2) for v in df["vol"].tolist()]
    pct = [round(v, 4) for v in df["pct_chg"].tolist()]
    vol_colors = ["#c62828" if p >= 0 else "#2e7d32" for p in pct]

    first_close = df.iloc[0]["close"]
    last_close = df.iloc[-1]["close"]
    return {
        "tsCode": df.iloc[0]["ts_code"],
        "dates": dates,
        "klineData": kline,
        "volData": vol,
        "pctData": pct,
        "volColors": vol_colors,
        "stats": {
            "start": dates[0][:4] + "-" + dates[0][4:6] + "-" + dates[0][6:],
            "end": dates[-1][:4] + "-" + dates[-1][4:6] + "-" + dates[-1][6:],
            "lastClose": round(last_close, 2),
            "highMax": round(float(df["high"].max()), 2),
            "lowMin": round(float(df["low"].min()), 2),
            "change": round(float(last_close - first_close), 2),
            "changePct": round(float((last_close - first_close) / first_close * 100), 2),
            "totalVol": round(float(df["vol"].sum() / 10000), 2),
            "days": len(df),
        },
    }


# ===== 模板 =====
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ title }}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,'Microsoft YaHei',sans-serif;background:#f0f2f5;color:#333}
.header{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:#fff;padding:24px 20px;text-align:center}
.header h1{font-size:22px;margin-bottom:4px}
.header p{font-size:13px;opacity:.75}
.search-bar{max-width:700px;margin:20px auto;background:#fff;border-radius:10px;padding:16px 20px;display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;box-shadow:0 1px 4px rgba(0,0,0,.06)}
.search-bar .field{display:flex;flex-direction:column;gap:4px}
.search-bar .field label{font-size:12px;font-weight:600;color:#666}
.search-bar .field input{padding:8px 12px;border:1px solid #ddd;border-radius:6px;font-size:14px;width:140px;outline:none}
.search-bar .field input:focus{border-color:#302b63}
.search-bar .field input.wide{width:200px}
.search-bar button{padding:8px 24px;border:none;border-radius:6px;font-size:14px;font-weight:600;cursor:pointer;background:#302b63;color:#fff;height:36px;transition:background .2s}
.search-bar button:hover{background:#1a1640}
.search-bar .hint{font-size:12px;color:#999;margin-left:auto;align-self:center}
.loading{text-align:center;padding:60px;color:#999;font-size:15px;display:none}
.loading .spinner{display:inline-block;width:32px;height:32px;border:3px solid #e0e0e0;border-top-color:#302b63;border-radius:50%;animation:spin .8s linear infinite;margin-bottom:12px}
@keyframes spin{to{transform:rotate(360deg)}}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;max-width:1100px;margin:0 auto 16px;padding:0 20px}
.stat-card{background:#fff;border-radius:8px;padding:12px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.stat-card .l{font-size:11px;color:#888;margin-bottom:2px}
.stat-card .v{font-size:18px;font-weight:700}
.stat-card .v.up{color:#c62828}
.stat-card .v.down{color:#2e7d32}
.charts{max-width:1100px;margin:0 auto;padding:0 20px 20px}
.chart-box{background:#fff;border-radius:10px;padding:16px;margin-bottom:14px;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.chart-box .ctitle{font-size:14px;font-weight:700;color:#333;margin-bottom:8px}
#klineChart{width:100%;height:420px}
#volumeChart{width:100%;height:130px}
#closeChart{width:100%;height:320px}
.error{max-width:700px;margin:20px auto;background:#fff0f0;border:1px solid #ffcdd2;border-radius:8px;padding:14px 18px;color:#c62828;display:none}
</style>
</head>
<body>

<div class="header">
    <h1>📊 股票日线行情看板</h1>
    <p id="subtitle">输入股票代码查看 K 线图与技术指标</p>
</div>

<div class="search-bar">
    <div class="field">
        <label>股票代码</label>
        <input class="wide" id="tscode" value="688256.SH" placeholder="例: 600519.SH / 000001.SZ / hk00700">
    </div>
    <div class="field">
        <label>月数</label>
        <input id="months" value="12" placeholder="12">
    </div>
    <button onclick="fetchData()">🔍 查询</button>
    <span class="hint">💡 格式：沪A sh600519 / 深A sz000001 / 港股 hk00700</span>
</div>

<div class="error" id="errorBox"></div>
<div class="loading" id="loading"><div class="spinner"></div>正在获取数据...</div>

<div id="content" style="display:none">
    <div class="stats" id="statsContainer"></div>
    <div class="charts">
        <div class="chart-box">
            <div class="ctitle">K 线图</div>
            <div id="klineChart"></div>
        </div>
        <div class="chart-box">
            <div class="ctitle">成交量</div>
            <div id="volumeChart"></div>
        </div>
        <div class="chart-box">
            <div class="ctitle">收盘价曲线</div>
            <div id="closeChart"></div>
        </div>
    </div>
</div>

<script>
const fmtD = d => d.substring(0,4)+'-'+d.substring(4,6)+'-'+d.substring(6,8);
const fmtP = v => '¥' + v.toFixed(2);
const fmtV = v => (v/10000).toFixed(2) + '万手';

async function fetchData() {
    const code = document.getElementById('tscode').value.trim();
    const months = document.getElementById('months').value || 12;
    if (!code) { showError('请输入股票代码'); return; }

    document.getElementById('errorBox').style.display = 'none';
    document.getElementById('content').style.display = 'none';
    document.getElementById('loading').style.display = 'block';
    document.getElementById('subtitle').textContent = '正在查询 ' + code + ' ...';

    try {
        const res = await fetch('/api/stock?tscode=' + encodeURIComponent(code) + '&months=' + months);
        const data = await res.json();
        if (data.error) { showError(data.error); return; }
        render(data);
    } catch(e) {
        showError('请求失败: ' + e.message);
    }
    document.getElementById('loading').style.display = 'none';
}

function showError(msg) {
    document.getElementById('loading').style.display = 'none';
    const box = document.getElementById('errorBox');
    box.textContent = msg;
    box.style.display = 'block';
}

function render(d) {
    document.getElementById('subtitle').textContent = d.tsCode + ' — ' + d.stats.start + ' ~ ' + d.stats.end;
    document.getElementById('content').style.display = 'block';

    // Stats
    const s = d.stats;
    document.getElementById('statsContainer').innerHTML = [
        {l:'起始日', v:s.start}, {l:'最新收盘', v:fmtP(s.lastClose), c:'up'},
        {l:'区间最高', v:fmtP(s.highMax)}, {l:'区间最低', v:fmtP(s.lowMin)},
        {l:'涨跌额', v:fmtP(s.change), c:s.change>=0?'up':'down'},
        {l:'涨跌幅', v:s.changePct+'%', c:s.change>=0?'up':'down'},
        {l:'总成交量', v:s.totalVol+'万手'}, {l:'交易日数', v:s.days+'天'}
    ].map(x => `<div class="stat-card"><div class="l">${x.l}</div><div class="v ${x.c||''}">${x.v}</div></div>`).join('');

    // K-line
    const kc = echarts.init(document.getElementById('klineChart'));
    kc.setOption({
        tooltip:{trigger:'axis',axisPointer:{type:'cross'},
            formatter:function(p){const i=p[0].dataIndex;
                return `<b>${fmtD(d.dates[i])}</b><br/>开盘：${fmtP(d.klineData[i][0])}<br/>收盘：${fmtP(d.klineData[i][1])}<br/>最高：${fmtP(d.klineData[i][3])}<br/>最低：${fmtP(d.klineData[i][2])}<br/>涨跌幅：<span style="color:${d.pctData[i]>=0?'#c62828':'#2e7d32'}">${d.pctData[i].toFixed(2)}%</span><br/>成交量：${fmtV(d.volData[i])}`;}},
        grid:{left:'12%',right:'8%',top:'10%',bottom:'6%'},
        xAxis:{type:'category',data:d.dates.map(fmtD),axisLabel:{rotate:45,fontSize:10,interval:Math.floor(d.dates.length/20)}},
        yAxis:{type:'value',scale:true,name:'价格 (¥)',nameLocation:'middle',nameGap:50,axisLabel:{formatter:'¥{value}'}},
        dataZoom:[{type:'inside',start:0,end:100},{type:'slider',start:0,end:100,bottom:0,height:18}],
        series:[{type:'candlestick',data:d.klineData,
            itemStyle:{color:'#c62828',color0:'#2e7d32',borderColor:'#c62828',borderColor0:'#2e7d32'}}]
    });

    // Volume
    const vc = echarts.init(document.getElementById('volumeChart'));
    vc.setOption({
        tooltip:{trigger:'axis',formatter:function(p){const i=p[0].dataIndex;return `<b>${fmtD(d.dates[i])}</b><br/>成交量：${fmtV(d.volData[i])}`;}},
        grid:{left:'12%',right:'8%',top:'18%',bottom:'6%'},
        xAxis:{type:'category',data:d.dates.map(fmtD),axisLabel:{show:false}},
        yAxis:{type:'value',name:'成交量 (手)',nameLocation:'middle',nameGap:55,axisLabel:{formatter:v=>(v/10000).toFixed(0)+'万'}},
        series:[{type:'bar',data:d.volData.map((v,i)=>({value:v,itemStyle:{color:d.volColors[i]}})),barWidth:'50%'}]
    });

    // Close price
    const closeP = d.klineData.map(x=>x[1]);
    const cc = echarts.init(document.getElementById('closeChart'));
    cc.setOption({
        tooltip:{trigger:'axis',formatter:function(p){const i=p[0].dataIndex;return `<b>${fmtD(d.dates[i])}</b><br/>收盘价：<span style="color:#2196F3;font-weight:700">${fmtP(closeP[i])}</span><br/>涨跌幅：<span style="color:${d.pctData[i]>=0?'#c62828':'#2e7d32'}">${d.pctData[i].toFixed(2)}%</span>`;}},
        grid:{left:'10%',right:'8%',top:'10%',bottom:'12%'},
        xAxis:{type:'category',data:d.dates.map(fmtD),axisLabel:{rotate:45,fontSize:10,interval:Math.floor(d.dates.length/20)}},
        yAxis:{type:'value',scale:true,name:'收盘价 (¥)',nameLocation:'middle',nameGap:55,axisLabel:{formatter:'¥{value}'}},
        dataZoom:[{type:'inside',start:0,end:100},{type:'slider',start:0,end:100,bottom:0,height:18}],
        series:[{type:'line',data:closeP,smooth:true,symbol:'none',lineStyle:{width:2,color:'#2196F3'},
            areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(33,150,243,0.25)'},{offset:1,color:'rgba(33,150,243,0.02)'}]}}}]
    });
}

// 默认加载
fetchData();
</script>
</body>
</html>"""


# ===== 路由 =====
@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE, title="股票日线行情看板")


@app.route("/api/stock")
def api_stock():
    tscode = request.args.get("tscode", "")
    months = int(request.args.get("months", 12))
    if not tscode:
        return jsonify({"error": "请提供股票代码"})
    try:
        df = fetch_kline(tscode, months)
        data = build_data_json(df)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)})


# ===== 启动 =====
if __name__ == "__main__":
    print("🚀 启动股票看板服务器...")
    print("   浏览器打开: http://localhost:5000")
    print("   示例代码: 688256.SH (寒武纪)")
    print("            600519.SH (贵州茅台)")
    print("            hk00700 (腾讯控股)")
    app.run(host="0.0.0.0", port=5000, debug=True)
