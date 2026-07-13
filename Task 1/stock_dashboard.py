#!/usr/bin/env python3
"""
股票行情看板 — 交互式 Web 应用（改进版）
========================================
支持任意 A 股/港股/美股股票，按股票名称或代码查询 K 线图、成交量、收盘价曲线。
新增: 股票名称搜索 + 输入建议下拉框。

用法：
  1. 设置 TUSHARE_TOKEN 环境变量（或在下方修改 TOKEN 变量）
  2. python stock_dashboard.py
  3. 浏览器打开 http://localhost:5000
"""

import os
import json
import re
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


# ===== 允许跨域（让 GitHub Pages 上的 Task 2 看板也能调用本地后端） =====
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

@app.route("/<path:p>", methods=["OPTIONS"])
def cors_preflight(p):
    return app.make_default_options_response()

# ===== 股票基础信息缓存 =====
_stock_cache = None  # list[dict], 每个 dict 包含 {code, name, market, fullCode}
_STOCK_CACHE_TIME = 3600  # 缓存有效期 1 小时
_last_cache_time = 0


_CACHE_FILE = os.path.join(os.path.dirname(__file__), ".stock_cache.json")


def load_stock_list() -> list[dict]:
    """
    加载 A 股基础信息列表（代码 + 名称），供搜索建议使用。
    优先从本地 JSON 文件读取缓存，避免频繁调用 Tushare API。
    """
    global _stock_cache, _last_cache_time
    now = datetime.now().timestamp()

    # 内存缓存命中
    if _stock_cache is not None and (now - _last_cache_time) < _STOCK_CACHE_TIME:
        return _stock_cache

    # 尝试从本地文件读取缓存
    file_cache_valid = False
    try:
        if os.path.exists(_CACHE_FILE):
            mtime = os.path.getmtime(_CACHE_FILE)
            if (now - mtime) < _STOCK_CACHE_TIME:
                with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                    _stock_cache = json.load(f)
                _last_cache_time = now
                file_cache_valid = True
                print(f"[信息] 从本地缓存加载 {len(_stock_cache)} 只股票")
    except Exception as e:
        print(f"[警告] 读取本地缓存失败: {e}")

    if file_cache_valid:
        return _stock_cache

    # 从 Tushare API 获取
    stocks = []
    try:
        df = pro.stock_basic(
            fields=["ts_code", "symbol", "name", "market", "list_status"]
        )
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                ts_code = row["ts_code"]      # 如 "688256.SH"
                sym = row["symbol"]           # 如 "688256"
                name = row["name"]            # 如 "寒武纪-U"
                market = row["market"]        # 主板/创业板/科创板
                stocks.append({
                    "code": sym,
                    "tsCode": ts_code,
                    "name": name,
                    "market": market,
                    "searchKey": f"{name} {sym} {ts_code}",
                })
    except Exception as e:
        print(f"[警告] 加载股票列表失败: {e}")

    stocks.sort(key=lambda x: x["code"])
    _stock_cache = stocks
    _last_cache_time = now

    # 写入本地文件缓存
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(stocks, f, ensure_ascii=False)
        print(f"[信息] 已保存 {len(stocks)} 只股票到本地缓存")
    except Exception as e:
        print(f"[警告] 写入本地缓存失败: {e}")

    print(f"[信息] 当前内存缓存: {len(stocks)} 只 A 股")
    return stocks


def resolve_tscode(query: str) -> str:
    """
    将用户输入解析为 Tushare 标准 ts_code。
    支持：
      - 中文名称 → 自动匹配股票 → 返回 ts_code
      - 纯数字6位 code → 自动补全后缀
      - 完整 ts_code → 直接返回
      - 简写如 sh600519 / 600519SH → 标准化
    """
    q = query.strip()
    if not q:
        return q

    # 情况 1: 已经是标准 ts_code 格式（6位数字 + .SH/.SZ/.BJ）
    if re.match(r"^\d{6}\.(SH|SZ|BJ)$", q.upper()):
        return q.upper()

    # 情况 2: 简写格式 sh600519 / sz000001 / 600519sh
    m = re.match(r"^([a-zA-Z]{2})?(\d{6})([a-zA-Z]{2})?$", q)
    if m:
        code = m.group(2)
        prefix = (m.group(1) or m.group(3) or "").upper()
        suffix_map = {"SH": ".SH", "SZ": ".SZ", "BJ": ".BJ",
                      "SH": ".SH", "SZ": ".SZ"}
        if prefix in suffix_map:
            return code + suffix_map[prefix]
        # 纯6位数字 → 从股票列表推断
        stocks = load_stock_list()
        for s in stocks:
            if s["code"] == code:
                return s["tsCode"]
        # 未知 → 默认上海
        return code + ".SH"

    # 情况 3: 港股格式 hk00700 → 保留原样
    if re.match(r"^(hk|HK|Hk)\d{5}$", q):
        return q

    # 情况 4: 中文名称 → 模糊匹配
    stocks = load_stock_list()
    matched = [s for s in stocks if q in s["name"] or q in s["code"]]
    if matched:
        # 取第一个精确匹配（名称完全相等优先）
        exact = [s for s in matched if s["name"] == q]
        if exact:
            return exact[0]["tsCode"]
        return matched[0]["tsCode"]

    # 都匹配不到就原样传给 Tushare，让 fetch_kline 报错
    return q


def fetch_kline(ts_code: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """
    从 Tushare 下载日线数据。
    start_date / end_date 格式: "YYYY-MM-DD" 或 "YYYYMMDD"
    如果未传，则默认拉取过去 1 年的数据。
    """
    # 规范化日期格式
    def norm(d):
        if d is None:
            return None
        d = d.strip().replace("-", "").replace("/", "")
        if len(d) != 8 or not d.isdigit():
            raise ValueError(f"日期格式错误，应为 YYYY-MM-DD 或 YYYYMMDD: {d}")
        return d

    start = norm(start_date) or (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
    end = norm(end_date) or datetime.now().strftime("%Y%m%d")
    df = pro.daily(
        ts_code=ts_code, start_date=start, end_date=end,
        fields=["ts_code", "trade_date", "open", "high", "low", "close",
                "pre_close", "change", "pct_chg", "vol", "amount"],
    )
    if df.empty:
        raise ValueError(f"未获取到 {ts_code} 在 {start}~{end} 之间的数据，请检查代码或日期范围")
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


def calc_indicators(df: pd.DataFrame, rsi_period: int = 14,
                    macd_fast: int = 12, macd_slow: int = 26, macd_signal: int = 9,
                    bb_period: int = 20, bb_k: float = 2.0) -> dict:
    """
    计算 RSI / MACD / 布林带 / KDJ 四大技术指标。
    返回前端友好的 dict。
    """
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    n = len(close)
    dates = df["trade_date"].tolist()

    # ----- 简单移动平均 (MA) -----
    ma5 = close.rolling(5).mean().round(2)
    ma10 = close.rolling(10).mean().round(2)
    ma20 = close.rolling(20).mean().round(2)
    ma60 = close.rolling(60).mean().round(2)

    # ----- RSI -----
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1/rsi_period, adjust=False, min_periods=rsi_period).mean()
    avg_loss = loss.ewm(alpha=1/rsi_period, adjust=False, min_periods=rsi_period).mean()
    rs = avg_gain / avg_loss
    rsi = (100 - 100 / (1 + rs)).round(2)

    # ----- MACD -----
    ema_fast = close.ewm(span=macd_fast, adjust=False).mean()
    ema_slow = close.ewm(span=macd_slow, adjust=False).mean()
    dif = (ema_fast - ema_slow).round(4)
    dea = dif.ewm(span=macd_signal, adjust=False).mean().round(4)
    macd_hist = ((dif - dea) * 2).round(4)

    # ----- 布林带 (BOLL) -----
    boll_mid = close.rolling(bb_period).mean().round(2)
    std = close.rolling(bb_period).std(ddof=0).round(2)
    boll_upper = (boll_mid + bb_k * std).round(2)
    boll_lower = (boll_mid - bb_k * std).round(2)

    # ----- KDJ -----
    low_n = low.rolling(9).min()
    high_n = high.rolling(9).max()
    rsv = ((close - low_n) / (high_n - low_n) * 100).round(2)
    k_line = rsv.ewm(alpha=1/3, adjust=False).mean().round(2)
    d_line = k_line.ewm(alpha=1/3, adjust=False).mean().round(2)
    j_line = (3 * k_line - 2 * d_line).round(2)

    def to_list(s, fill_nan=True):
        """转 list，None 填 null（前端能识别）"""
        out = []
        for v in s.tolist():
            if pd.isna(v):
                out.append(None)
            else:
                out.append(float(v))
        return out

    return {
        "dates": [d[:4] + "-" + d[4:6] + "-" + d[6:] for d in dates],
        "kline": [[round(float(r["open"]), 2), round(float(r["close"]), 2),
                   round(float(r["low"]), 2), round(float(r["high"]), 2)]
                  for _, r in df.iterrows()],
        "ma": {
            "ma5": to_list(ma5),
            "ma10": to_list(ma10),
            "ma20": to_list(ma20),
            "ma60": to_list(ma60),
        },
        "rsi": {
            "period": rsi_period,
            "values": to_list(rsi),
        },
        "macd": {
            "fast": macd_fast, "slow": macd_slow, "signal": macd_signal,
            "dif": to_list(dif),
            "dea": to_list(dea),
            "hist": to_list(macd_hist),
        },
        "boll": {
            "period": bb_period, "k": bb_k,
            "upper": to_list(boll_upper),
            "mid": to_list(boll_mid),
            "lower": to_list(boll_lower),
        },
        "kdj": {
            "k": to_list(k_line),
            "d": to_list(d_line),
            "j": to_list(j_line),
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
body{font-family:-apple-system,'Microsoft YaHei','PingFang SC',sans-serif;background:#f4f5f7;color:#1f2329;}

/* 头部：同花顺风格的简洁白底 */
.header{background:#fff;color:#1f2329;padding:14px 24px;border-bottom:1px solid #e6e8eb;display:flex;align-items:center;gap:14px}
.header .logo{width:28px;height:28px;background:#e63946;border-radius:6px;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:16px}
.header h1{font-size:18px;font-weight:600;color:#1f2329;margin:0;letter-spacing:.3px}
.header .sep{color:#c9cdd4;font-size:14px}
.header .stock-info{font-size:13px;color:#4e5969;display:flex;align-items:center;gap:10px}
.header .stock-info .code{color:#1f2329;font-weight:600}
.header .stock-info .name{color:#4e5969}
.header .stock-info .date{color:#86909c;font-size:12px}

/* 容器：统一最大宽度 */
.container{max-width:1280px;margin:0 auto;padding:16px 20px}

/* 控制面板：等宽网格布局 */
.search-bar{background:#fff;border:1px solid #e6e8eb;border-radius:6px;padding:14px 18px;margin-bottom:14px;display:grid;grid-template-columns:repeat(12,1fr);gap:14px;align-items:end}
.search-bar .field{display:flex;flex-direction:column;gap:5px;position:relative}
.search-bar .field label{font-size:12px;font-weight:500;color:#4e5969}
.search-bar .field input,
.search-bar .field select{padding:7px 10px;border:1px solid #c9cdd4;border-radius:4px;font-size:13px;outline:none;background:#fff;height:32px;transition:border-color .15s}
.search-bar .field input:focus,
.search-bar .field select:focus{border-color:#3370ff}
.search-bar .field.col-3{grid-column:span 3}
.search-bar .field.col-4{grid-column:span 4}
.search-bar .field.col-5{grid-column:span 5}
.search-bar .field.col-12{grid-column:span 12}
.search-bar .field .suggest-box{position:absolute;top:100%;left:0;right:0;background:#fff;border:1px solid #e6e8eb;border-radius:4px;max-height:260px;overflow-y:auto;z-index:1000;display:none;box-shadow:0 4px 12px rgba(0,0,0,0.1);margin-top:2px}
.search-bar .field .suggest-box.active{display:block}
.search-bar .field .suggest-item{padding:7px 12px;cursor:pointer;font-size:13px;border-bottom:1px solid #f0f1f3;display:flex;justify-content:space-between;align-items:center}
.search-bar .field .suggest-item:hover{background:#f2f4f7}
.search-bar .field .suggest-item .scode{color:#1f2329;font-weight:600;font-size:12px}
.search-bar .field .suggest-item .sname{color:#4e5969}
.search-bar .field .suggest-item .smarket{font-size:11px;color:#86909c}
.search-bar button{height:32px;border:none;border-radius:4px;font-size:13px;font-weight:500;cursor:pointer;transition:all .15s;padding:0 16px}
.search-bar .btn-primary{background:#3370ff;color:#fff}
.search-bar .btn-primary:hover{background:#1d5ce0}
.search-bar .preset-group{display:flex;gap:6px;flex-wrap:wrap}
.search-bar .preset-btn{padding:5px 10px;border:1px solid #c9cdd4;background:#fff;border-radius:3px;font-size:12px;color:#4e5969;cursor:pointer;transition:all .15s;height:32px}
.search-bar .preset-btn:hover{border-color:#3370ff;color:#3370ff}
.search-bar .preset-btn.active{background:#e8f0ff;border-color:#3370ff;color:#3370ff}
.search-bar .hint{font-size:12px;color:#86909c;align-self:center;grid-column:span 12}

/* 错误/加载 */
.error-msg{background:#fff2f0;border:1px solid #ffccc7;border-radius:4px;padding:10px 16px;color:#cf1322;margin-bottom:12px;display:none;font-size:13px}
.error-msg.active{display:block}
.loading{text-align:center;padding:50px;color:#86909c;font-size:14px;display:none}
.loading.active{display:block}
.loading .spinner{display:inline-block;width:28px;height:28px;border:2px solid #e6e8eb;border-top-color:#3370ff;border-radius:50%;animation:spin .8s linear infinite;margin-bottom:10px}
@keyframes spin{to{transform:rotate(360deg)}}

/* 统计卡片 */
.stats{display:grid;grid-template-columns:repeat(8,1fr);gap:1px;background:#e6e8eb;border:1px solid #e6e8eb;border-radius:6px;margin-bottom:14px;overflow:hidden}
.stat-card{background:#fff;padding:14px 12px;text-align:left}
.stat-card .l{font-size:12px;color:#86909c;margin-bottom:4px}
.stat-card .v{font-size:18px;font-weight:600;color:#1f2329;font-family:-apple-system,SF Pro Display,Roboto,sans-serif}
.stat-card .v.up{color:#e63946}
.stat-card .v.down{color:#16a34a}

/* 图表卡片 */
.charts{display:grid;grid-template-columns:1fr;gap:14px}
.chart-box{background:#fff;border:1px solid #e6e8eb;border-radius:6px;padding:14px 16px}
.chart-box .ctitle{font-size:14px;font-weight:600;color:#1f2329;margin-bottom:10px;display:flex;align-items:center;gap:6px}
.chart-box .ctitle::before{content:"";display:inline-block;width:3px;height:14px;background:#3370ff;border-radius:2px}
#klineChart{width:100%;height:460px}
#volumeChart{width:100%;height:140px}
#closeChart{width:100%;height:300px}

/* 数据表格 */
.data-table{background:#fff;border:1px solid #e6e8eb;border-radius:6px;margin-top:14px;overflow:hidden}
.data-table .table-header{padding:12px 16px;border-bottom:1px solid #e6e8eb;display:flex;justify-content:space-between;align-items:center}
.data-table .table-title{font-size:14px;font-weight:600;color:#1f2329;display:flex;align-items:center;gap:6px}
.data-table .table-title::before{content:"";display:inline-block;width:3px;height:14px;background:#3370ff;border-radius:2px}
.data-table .table-meta{font-size:12px;color:#86909c}
.data-table .table-wrap{max-height:480px;overflow-y:auto}
.data-table .table-wrap::-webkit-scrollbar{width:8px;height:8px}
.data-table .table-wrap::-webkit-scrollbar-thumb{background:#c9cdd4;border-radius:4px}
.data-table .table-wrap::-webkit-scrollbar-track{background:#f0f1f3}
.data-table table{width:100%;border-collapse:collapse;font-size:12px;font-family:-apple-system,SF Pro Display,Roboto,sans-serif}
.data-table thead{position:sticky;top:0;background:#f7f8fa;z-index:1}
.data-table th{padding:10px 12px;text-align:right;font-weight:500;color:#4e5969;border-bottom:1px solid #e6e8eb;white-space:nowrap;font-size:12px}
.data-table th:first-child{text-align:center}
.data-table td{padding:9px 12px;text-align:right;border-bottom:1px solid #f0f1f3;white-space:nowrap;color:#1f2329}
.data-table td:first-child{text-align:center;color:#4e5969}
.data-table tr:hover{background:#fafbfc}
.data-table .up{color:#e63946}
.data-table .down{color:#16a34a}
.data-table .highlight-row{background:#f0f7ff}

@media (max-width:900px){
  .search-bar{grid-template-columns:repeat(6,1fr)}
  .search-bar .field.col-3,.search-bar .field.col-4,.search-bar .field.col-5,.search-bar .field.col-12{grid-column:span 6}
  .stats{grid-template-columns:repeat(4,1fr)}
}
</style>
</head>
<body>

<div class="header">
    <div class="logo">K</div>
    <h1>股票日线行情</h1>
    <span class="sep">|</span>
    <div class="stock-info">
        <span class="code" id="headerCode">688256.SH</span>
        <span class="name" id="headerName">寒武纪</span>
        <span class="date" id="headerDate">--</span>
    </div>
</div>

<div class="container">

    <!-- 控制面板 -->
    <div class="search-bar">
        <div class="field col-3">
            <label>股票代码 / 名称</label>
            <input id="stockInput" value="688256.SH"
                   placeholder="例: 寒武纪 / 600519 / 00700"
                   autocomplete="off">
            <div class="suggest-box" id="suggestBox"></div>
        </div>
        <div class="field col-4">
            <label>开始日期</label>
            <div style="display:flex;gap:4px;align-items:center;">
                <select id="startYear" style="flex:1;min-width:0;"></select>
                <select id="startMonth" style="flex:1;min-width:0;"></select>
                <select id="startDay" style="flex:1;min-width:0;"></select>
            </div>
        </div>
        <div class="field col-4">
            <label>结束日期</label>
            <div style="display:flex;gap:4px;align-items:center;">
                <select id="endYear" style="flex:1;min-width:0;"></select>
                <select id="endMonth" style="flex:1;min-width:0;"></select>
                <select id="endDay" style="flex:1;min-width:0;"></select>
            </div>
        </div>
        <div class="field col-1">
            <label>&nbsp;</label>
            <button class="btn-primary" onclick="fetchData()">查询</button>
        </div>
        <div class="field col-12">
            <label>快捷范围</label>
            <div class="preset-group">
                <button type="button" class="preset-btn" data-preset="1m">近1月</button>
                <button type="button" class="preset-btn" data-preset="3m">近3月</button>
                <button type="button" class="preset-btn" data-preset="6m">近6月</button>
                <button type="button" class="preset-btn" data-preset="1y">近1年</button>
                <button type="button" class="preset-btn" data-preset="2y">近2年</button>
                <button type="button" class="preset-btn" data-preset="all">全部</button>
            </div>
        </div>
    </div>

    <div class="error-msg" id="errorBox"></div>
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
        <div class="data-table">
            <div class="table-header">
                <div class="table-title">详细数据</div>
                <div class="table-meta" id="tableMeta">--</div>
            </div>
            <div class="table-wrap" id="dataTableWrap"></div>
        </div>
    </div>

</div>

<script>
const fmtD = d => d.substring(0,4)+'-'+d.substring(4,6)+'-'+d.substring(6,8);
const fmtP = v => '¥' + v.toFixed(2);
const fmtV = v => (v/10000).toFixed(2) + '万手';

let searchTimer = null;
let selectedTsCode = '';

// ===== 搜索建议 =====
document.getElementById('stockInput').addEventListener('input', function(e) {
    clearTimeout(searchTimer);
    const val = e.target.value.trim();
    if (val.length < 1) {
        document.getElementById('suggestBox').classList.remove('active');
        return;
    }
    searchTimer = setTimeout(() => doSearch(val), 250);
});

document.getElementById('stockInput').addEventListener('keydown', function(e) {
    const box = document.getElementById('suggestBox');
    if (!box.classList.contains('active')) return;
    const items = box.querySelectorAll('.suggest-item');
    if (items.length === 0) return;
    let idx = Array.from(items).findIndex(el => el.classList.contains('hover'));
    if (e.key === 'ArrowDown') {
        e.preventDefault();
        idx = Math.min(idx + 1, items.length - 1);
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        idx = Math.max(idx - 1, 0);
    } else if (e.key === 'Enter') {
        e.preventDefault();
        if (idx >= 0) items[idx].click();
        return;
    } else return;
    items.forEach(el => el.classList.remove('hover'));
    items[idx].classList.add('hover');
    items[idx].scrollIntoView({block: 'nearest'});
});

document.addEventListener('click', function(e) {
    if (!document.getElementById('stockInput').contains(e.target)) {
        document.getElementById('suggestBox').classList.remove('active');
    }
});

async function doSearch(keyword) {
    const box = document.getElementById('suggestBox');
    try {
        const resp = await fetch('/api/search?q=' + encodeURIComponent(keyword));
        const data = await resp.json();
        if (!data.stocks || data.stocks.length === 0) {
            box.classList.remove('active');
            return;
        }
        box.innerHTML = data.stocks.map(s =>
            `<div class="suggest-item" onclick="selectStock('${s.tsCode}', '${s.name}')">
                <span><span class="sname">${s.name}</span> <span class="scode">${s.code}</span></span>
                <span class="smarket">${s.market || ''}</span>
            </div>`
        ).join('');
        box.classList.add('active');
    } catch(e) {
        box.classList.remove('active');
    }
}

function selectStock(tsCode, name) {
    selectedTsCode = tsCode;
    document.getElementById('stockInput').value = name;
    document.getElementById('suggestBox').classList.remove('active');
    fetchData();
}

// ===== 日期下拉框初始化 =====
function pad2(n) { return String(n).padStart(2, '0'); }

function daysInMonth(year, month) {
    return new Date(year, month, 0).getDate();
}

function initDateSelects() {
    const now = new Date();
    const curY = now.getFullYear();
    // 起始范围：1990 ~ 当前年
    const minY = 1990;
    const maxY = curY;
    const startY = document.getElementById('startYear');
    const startM = document.getElementById('startMonth');
    const startD = document.getElementById('startDay');
    const endY = document.getElementById('endYear');
    const endM = document.getElementById('endMonth');
    const endD = document.getElementById('endDay');

    function fillYear(sel) {
        sel.innerHTML = '';
        for (let y = minY; y <= maxY; y++) {
            const opt = document.createElement('option');
            opt.value = y; opt.textContent = y;
            sel.appendChild(opt);
        }
    }
    function fillMonth(sel) {
        sel.innerHTML = '';
        for (let m = 1; m <= 12; m++) {
            const opt = document.createElement('option');
            opt.value = m; opt.textContent = m;
            sel.appendChild(opt);
        }
    }
    function fillDay(sel, y, m) {
        sel.innerHTML = '';
        const d = daysInMonth(y, m);
        for (let day = 1; day <= d; day++) {
            const opt = document.createElement('option');
            opt.value = day; opt.textContent = day;
            sel.appendChild(opt);
        }
    }

    fillYear(startY); fillYear(endY);
    fillMonth(startM); fillMonth(endM);
    fillDay(startD, curY - 1, now.getMonth() + 1);
    fillDay(endD, curY, now.getMonth() + 1);

    // 默认：开始 = 一年前今天；结束 = 今天
    startY.value = curY - 1;
    startM.value = now.getMonth() + 1;
    startD.value = Math.min(now.getDate(), daysInMonth(curY - 1, now.getMonth() + 1));
    endY.value = curY;
    endM.value = now.getMonth() + 1;
    endD.value = now.getDate();

    function refreshDays() {
        fillDay(startD, parseInt(startY.value), parseInt(startM.value));
        if (parseInt(startD.value) > daysInMonth(parseInt(startY.value), parseInt(startM.value))) {
            startD.value = daysInMonth(parseInt(startY.value), parseInt(startM.value));
        }
    }
    function refreshDaysEnd() {
        fillDay(endD, parseInt(endY.value), parseInt(endM.value));
        if (parseInt(endD.value) > daysInMonth(parseInt(endY.value), parseInt(endM.value))) {
            endD.value = daysInMonth(parseInt(endY.value), parseInt(endM.value));
        }
    }
    startY.addEventListener('change', refreshDays);
    startM.addEventListener('change', refreshDays);
    endY.addEventListener('change', refreshDaysEnd);
    endM.addEventListener('change', refreshDaysEnd);
}

function applyPreset(preset) {
    const now = new Date();
    const curY = now.getFullYear();
    const curM = now.getMonth() + 1;
    const curD = now.getDate();
    const startY = document.getElementById('startYear');
    const startM = document.getElementById('startMonth');
    const startD = document.getElementById('startDay');
    const endY = document.getElementById('endYear');
    const endM = document.getElementById('endMonth');
    const endD = document.getElementById('endDay');

    endY.value = curY; endM.value = curM; endD.value = curD;

    let sy = curY, sm = curM, sd = curD;
    if (preset === '1m') sm -= 1;
    else if (preset === '3m') sm -= 3;
    else if (preset === '6m') sm -= 6;
    else if (preset === '1y') sy -= 1;
    else if (preset === '2y') sy -= 2;
    else if (preset === 'all') { sy = 1990; sm = 1; sd = 1; }

    while (sm <= 0) { sm += 12; sy -= 1; }
    startY.value = sy;
    startM.value = sm;
    // 月初
    startD.value = 1;
    // 触发日刷新
    const evt = new Event('change');
    startY.dispatchEvent(evt);
    startM.dispatchEvent(evt);

    // 触发高亮
    setActivePreset(preset);

    fetchData();
}

function getDateRange() {
    const sy = document.getElementById('startYear').value;
    const sm = pad2(document.getElementById('startMonth').value);
    const sd = pad2(document.getElementById('startDay').value);
    const ey = document.getElementById('endYear').value;
    const em = pad2(document.getElementById('endMonth').value);
    const ed = pad2(document.getElementById('endDay').value);
    return {
        start: `${sy}-${sm}-${sd}`,
        end: `${ey}-${em}-${ed}`,
    };
}

function setActivePreset(preset) {
    document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
    const btn = document.querySelector(`.preset-btn[data-preset="${preset}"]`);
    if (btn) btn.classList.add('active');
}

// ===== 查询 =====
async function fetchData() {
    let code = document.getElementById('stockInput').value.trim();
    if (selectedTsCode) code = selectedTsCode;
    if (!code) { showError('请输入股票名称或代码'); return; }

    const { start, end } = getDateRange();
    if (start > end) { showError('开始日期不能晚于结束日期'); return; }

    document.getElementById('errorBox').classList.remove('active');
    document.getElementById('content').style.display = 'none';
    document.getElementById('loading').classList.add('active');
    document.getElementById('headerCode').textContent = code;
    document.getElementById('headerName').textContent = '加载中...';
    document.getElementById('headerDate').textContent = start + ' ~ ' + end;

    try {
        const res = await fetch('/api/stock?tscode=' + encodeURIComponent(code) +
            '&start_date=' + encodeURIComponent(start) +
            '&end_date=' + encodeURIComponent(end));
        const data = await res.json();
        if (data.error) { showError(data.error); return; }
        selectedTsCode = '';
        render(data);
    } catch(e) {
        showError('请求失败: ' + e.message);
    }
    document.getElementById('loading').classList.remove('active');
}

function showError(msg) {
    document.getElementById('loading').classList.remove('active');
    const box = document.getElementById('errorBox');
    box.textContent = msg;
    box.classList.add('active');
}

function render(d) {
    // 头部信息
    document.getElementById('headerCode').textContent = d.tsCode;
    document.getElementById('headerName').textContent = d.tsCode.split('.')[0];
    document.getElementById('headerDate').textContent = d.stats.start + ' ~ ' + d.stats.end;
    document.getElementById('content').style.display = 'block';

    // 统计卡片
    const s = d.stats;
    document.getElementById('statsContainer').innerHTML = [
        {l:'起始日', v:s.start},
        {l:'最新收盘', v:fmtP(s.lastClose)},
        {l:'区间最高', v:fmtP(s.highMax)},
        {l:'区间最低', v:fmtP(s.lowMin)},
        {l:'涨跌额', v:fmtP(s.change), c:s.change>=0?'up':'down'},
        {l:'涨跌幅', v:(s.changePct>=0?'+':'')+s.changePct+'%', c:s.changePct>=0?'up':'down'},
        {l:'总成交量', v:s.totalVol+'万手'},
        {l:'交易日数', v:s.days+'天'},
    ].map(x => `<div class="stat-card"><div class="l">${x.l}</div><div class="v ${x.c||''}">${x.v}</div></div>`).join('');

    // 详细数据表格（可滚动）
    const rows = d.dates.map((dt, i) => {
        const k = d.klineData[i];
        const close = k[1], open = k[0], high = k[3], low = k[2];
        const pct = d.pctData[i];
        const vol = d.volData[i];
        const cls = pct >= 0 ? 'up' : 'down';
        const sign = pct >= 0 ? '+' : '';
        return `<tr>
            <td>${fmtD(dt)}</td>
            <td>${open.toFixed(2)}</td>
            <td class="${cls}">${close.toFixed(2)}</td>
            <td>${high.toFixed(2)}</td>
            <td>${low.toFixed(2)}</td>
            <td class="${cls}">${sign}${pct.toFixed(2)}%</td>
            <td>${(vol/10000).toFixed(0)}</td>
            <td class="${cls}">${close > open ? '↑' : (close < open ? '↓' : '—')}</td>
        </tr>`;
    }).reverse().join('');
    document.getElementById('dataTableWrap').innerHTML =
        `<table><thead><tr>
            <th>日期</th><th>开盘</th><th>收盘</th><th>最高</th><th>最低</th>
            <th>涨跌幅</th><th>成交量(手)</th><th>方向</th>
        </tr></thead><tbody>${rows}</tbody></table>`;
    document.getElementById('tableMeta').textContent = `共 ${d.dates.length} 条交易数据 · 显示最新 ${Math.min(d.dates.length, 50)} 条`;

    // K-line
    const kc = echarts.init(document.getElementById('klineChart'));
    kc.setOption({
        tooltip:{trigger:'axis',axisPointer:{type:'cross'},
            formatter:function(p){const i=p[0].dataIndex;
                return `<b>${fmtD(d.dates[i])}</b><br/>开盘：${fmtP(d.klineData[i][0])}<br/>收盘：<span style="color:${d.pctData[i]>=0?'#e63946':'#16a34a'};font-weight:600">${fmtP(d.klineData[i][1])}</span><br/>最高：${fmtP(d.klineData[i][3])}<br/>最低：${fmtP(d.klineData[i][2])}<br/>涨跌幅：<span style="color:${d.pctData[i]>=0?'#e63946':'#16a34a'}">${d.pctData[i].toFixed(2)}%</span><br/>成交量：${fmtV(d.volData[i])}`;}},
        grid:{left:'10%',right:'4%',top:'6%',bottom:'12%'},
        xAxis:{type:'category',data:d.dates.map(fmtD),axisLabel:{rotate:0,fontSize:10,interval:Math.floor(d.dates.length/12)},axisLine:{lineStyle:{color:'#e6e8eb'}}},
        yAxis:{type:'value',scale:true,axisLabel:{formatter:'¥{value}',color:'#4e5969'},splitLine:{lineStyle:{color:'#f0f1f3'}}},
        dataZoom:[{type:'inside',start:0,end:100},{type:'slider',start:0,end:100,bottom:2,height:18,borderColor:'#c9cdd4',fillerColor:'rgba(51,112,255,0.1)'}],
        series:[{type:'candlestick',data:d.klineData,
            itemStyle:{color:'#e63946',color0:'#16a34a',borderColor:'#e63946',borderColor0:'#16a34a'}}]
    });

    // Volume
    const vc = echarts.init(document.getElementById('volumeChart'));
    vc.setOption({
        tooltip:{trigger:'axis',formatter:function(p){const i=p[0].dataIndex;return `<b>${fmtD(d.dates[i])}</b><br/>成交量：${fmtV(d.volData[i])}`;}},
        grid:{left:'10%',right:'4%',top:'18%',bottom:'2%'},
        xAxis:{type:'category',data:d.dates.map(fmtD),axisLabel:{show:false},axisLine:{show:false}},
        yAxis:{type:'value',axisLabel:{formatter:v=>(v/10000).toFixed(0)+'万',color:'#86909c'},splitLine:{lineStyle:{color:'#f0f1f3'}}},
        series:[{type:'bar',data:d.volData.map((v,i)=>({value:v,itemStyle:{color:d.volColors[i]}})),barWidth:'60%'}]
    });

    // Close price
    const closeP = d.klineData.map(x=>x[1]);
    const cc = echarts.init(document.getElementById('closeChart'));
    cc.setOption({
        tooltip:{trigger:'axis',formatter:function(p){const i=p[0].dataIndex;return `<b>${fmtD(d.dates[i])}</b><br/>收盘价：<span style="color:#3370ff;font-weight:600">${fmtP(closeP[i])}</span><br/>涨跌幅：<span style="color:${d.pctData[i]>=0?'#e63946':'#16a34a'}">${d.pctData[i].toFixed(2)}%</span>`;}},
        grid:{left:'10%',right:'4%',top:'6%',bottom:'12%'},
        xAxis:{type:'category',data:d.dates.map(fmtD),axisLabel:{rotate:0,fontSize:10,interval:Math.floor(d.dates.length/12)},axisLine:{lineStyle:{color:'#e6e8eb'}}},
        yAxis:{type:'value',scale:true,axisLabel:{formatter:'¥{value}',color:'#4e5969'},splitLine:{lineStyle:{color:'#f0f1f3'}}},
        dataZoom:[{type:'inside',start:0,end:100},{type:'slider',start:0,end:100,bottom:2,height:18,borderColor:'#c9cdd4',fillerColor:'rgba(51,112,255,0.1)'}],
        series:[{type:'line',data:closeP,smooth:true,symbol:'none',lineStyle:{width:2,color:'#3370ff'},
            areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(51,112,255,0.18)'},{offset:1,color:'rgba(51,112,255,0.02)'}]}}}]
    });

    // 图表随窗口缩放
    window.addEventListener('resize', () => { kc.resize(); vc.resize(); cc.resize(); });
}

// 默认加载
document.querySelectorAll('.preset-btn').forEach(btn => {
    btn.addEventListener('click', () => applyPreset(btn.dataset.preset));
});
initDateSelects();
setActivePreset('1y');
fetchData();
</script>
</body>
</html>"""


# ===== 路由 =====
@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE, title="股票日线行情看板")


@app.route("/api/search")
def api_search():
    """
    搜索股票建议 — 支持按名称或代码模糊匹配。
    返回最多 15 条建议。
    """
    q = request.args.get("q", "").strip()
    if not q or len(q) < 1:
        return jsonify({"stocks": []})
    stocks = load_stock_list()
    q_lower = q.lower()
    matched = [s for s in stocks if q_lower in s["searchKey"].lower()]
    # 按匹配度排序：名称前缀 > 代码前缀 > 名称包含 > 代码包含
    def sort_key(s):
        n = s["name"]
        c = s["code"]
        if n.startswith(q) or c.startswith(q):
            return 0
        if q in n:
            return 1
        if q in c:
            return 2
        return 3
    matched.sort(key=sort_key)
    return jsonify({"stocks": matched[:15]})


@app.route("/api/stock")
def api_stock():
    tscode = request.args.get("tscode", "")
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")
    if not tscode:
        return jsonify({"error": "请提供股票代码"})
    try:
        # 尝试将用户输入解析为标准 ts_code（支持中文名称等）
        resolved = resolve_tscode(tscode)
        df = fetch_kline(
            resolved,
            start_date=start_date or None,
            end_date=end_date or None,
        )
        data = build_data_json(df)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/indicators")
def api_indicators():
    """
    返回 RSI / MACD / 布林带 / KDJ / MA 五大技术指标。
    参数:
      tscode: 股票代码或中文名
      start_date / end_date: YYYY-MM-DD（可选）
      rsi_period, macd_fast, macd_slow, macd_signal, bb_period, bb_k: 可调参数
    """
    tscode = request.args.get("tscode", "")
    if not tscode:
        return jsonify({"error": "请提供股票代码"})
    try:
        rsi_period = int(request.args.get("rsi_period", 14))
        macd_fast = int(request.args.get("macd_fast", 12))
        macd_slow = int(request.args.get("macd_slow", 26))
        macd_signal = int(request.args.get("macd_signal", 9))
        bb_period = int(request.args.get("bb_period", 20))
        bb_k = float(request.args.get("bb_k", 2.0))

        resolved = resolve_tscode(tscode)
        df = fetch_kline(
            resolved,
            start_date=request.args.get("start_date") or None,
            end_date=request.args.get("end_date") or None,
        )
        ind = calc_indicators(
            df, rsi_period=rsi_period, macd_fast=macd_fast,
            macd_slow=macd_slow, macd_signal=macd_signal,
            bb_period=bb_period, bb_k=bb_k,
        )
        ind["tsCode"] = df.iloc[0]["ts_code"]
        return jsonify(ind)
    except Exception as e:
        return jsonify({"error": str(e)})


# ===== 启动 =====
if __name__ == "__main__":
    # 启动时预加载股票列表（首次会稍慢，后续自动缓存）
    print("🚀 正在预加载股票基础信息（约 5000+ 只 A 股）...")
    try:
        count = len(load_stock_list())
        print(f"   ✅ 已加载 {count} 只股票")
    except Exception as e:
        print(f"   ⚠️ 加载股票列表失败（不影响查询，仅搜索建议不可用）: {e}")
    print("📊 启动股票看板服务器...")
    print("   浏览器打开: http://localhost:5000")
    print("   支持中文名称 / 6位代码 / sh/sz前缀 / Tushare标准代码")
    app.run(host="0.0.0.0", port=5000, debug=False)
