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
.search-bar .field{display:flex;flex-direction:column;gap:4px;position:relative}
.search-bar .field label{font-size:12px;font-weight:600;color:#666}
.search-bar .field input{padding:8px 12px;border:1px solid #ddd;border-radius:6px;font-size:14px;width:200px;outline:none}
.search-bar .field input:focus{border-color:#302b63}
.search-bar .field input.wide{width:260px}
.search-bar .field .suggest-box{position:absolute;top:100%;left:0;right:0;background:#fff;border:1px solid #ddd;border-radius:6px;max-height:260px;overflow-y:auto;z-index:1000;display:none;box-shadow:0 4px 16px rgba(0,0,0,0.12)}
.search-bar .field .suggest-box.active{display:block}
.search-bar .field .suggest-item{padding:8px 14px;cursor:pointer;font-size:13px;border-bottom:1px solid #f3f3f3;display:flex;justify-content:space-between;align-items:center}
.search-bar .field .suggest-item:hover{background:#f0f4ff}
.search-bar .field .suggest-item .scode{color:#302b63;font-weight:600;font-size:12px}
.search-bar .field .suggest-item .sname{color:#333}
.search-bar .field .suggest-item .smarket{font-size:11px;color:#999}
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
    <p id="subtitle">输入股票名称或代码，查看 K 线图与技术指标</p>
</div>

<div class="search-bar">
    <div class="field">
        <label>股票名称 / 代码</label>
        <input class="wide" id="stockInput" value="688256.SH"
               placeholder="例: 寒武纪 / 贵州茅台 / 600519 / 00700"
               autocomplete="off">
        <div class="suggest-box" id="suggestBox"></div>
    </div>
    <div class="field" style="min-width:240px;">
        <label>📅 时间范围</label>
        <div style="display:flex;gap:4px;align-items:center;flex-wrap:nowrap;">
            <select id="startYear" style="width:78px;padding:7px 6px;border:1px solid #ddd;border-radius:6px;font-size:13px;outline:none;"></select>
            <span style="color:#888;font-size:12px;">年</span>
            <select id="startMonth" style="width:64px;padding:7px 6px;border:1px solid #ddd;border-radius:6px;font-size:13px;outline:none;"></select>
            <span style="color:#888;font-size:12px;">月</span>
            <select id="startDay" style="width:64px;padding:7px 6px;border:1px solid #ddd;border-radius:6px;font-size:13px;outline:none;"></select>
            <span style="color:#888;font-size:12px;">日</span>
        </div>
    </div>
    <div class="field" style="min-width:240px;">
        <label>&nbsp;</label>
        <div style="display:flex;gap:4px;align-items:center;flex-wrap:nowrap;">
            <span style="color:#888;font-size:12px;">至</span>
            <select id="endYear" style="width:78px;padding:7px 6px;border:1px solid #ddd;border-radius:6px;font-size:13px;outline:none;"></select>
            <span style="color:#888;font-size:12px;">年</span>
            <select id="endMonth" style="width:64px;padding:7px 6px;border:1px solid #ddd;border-radius:6px;font-size:13px;outline:none;"></select>
            <span style="color:#888;font-size:12px;">月</span>
            <select id="endDay" style="width:64px;padding:7px 6px;border:1px solid #ddd;border-radius:6px;font-size:13px;outline:none;"></select>
            <span style="color:#888;font-size:12px;">日</span>
        </div>
    </div>
    <div class="field">
        <label>&nbsp;</label>
        <div style="display:flex;gap:4px;flex-wrap:wrap;">
            <button type="button" class="preset-btn" data-preset="1m" style="padding:6px 10px;border:1px solid #ddd;background:#fff;border-radius:5px;font-size:12px;cursor:pointer;">近1月</button>
            <button type="button" class="preset-btn" data-preset="3m" style="padding:6px 10px;border:1px solid #ddd;background:#fff;border-radius:5px;font-size:12px;cursor:pointer;">近3月</button>
            <button type="button" class="preset-btn" data-preset="6m" style="padding:6px 10px;border:1px solid #ddd;background:#fff;border-radius:5px;font-size:12px;cursor:pointer;">近6月</button>
            <button type="button" class="preset-btn" data-preset="1y" style="padding:6px 10px;border:1px solid #ddd;background:#fff;border-radius:5px;font-size:12px;cursor:pointer;">近1年</button>
            <button type="button" class="preset-btn" data-preset="2y" style="padding:6px 10px;border:1px solid #ddd;background:#fff;border-radius:5px;font-size:12px;cursor:pointer;">近2年</button>
            <button type="button" class="preset-btn" data-preset="all" style="padding:6px 10px;border:1px solid #ddd;background:#fff;border-radius:5px;font-size:12px;cursor:pointer;">全部</button>
        </div>
    </div>
    <div class="field">
        <label>&nbsp;</label>
        <button onclick="fetchData()" style="padding:8px 24px;border:none;border-radius:6px;font-size:14px;font-weight:600;cursor:pointer;background:#302b63;color:#fff;height:36px;transition:background .2s;">🔍 查询</button>
    </div>
    <span class="hint">💡 支持中文名称、6位代码、sh/sz/hk 前缀</span>
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
    document.querySelectorAll('.preset-btn').forEach(b => {
        b.style.background = '#fff';
        b.style.borderColor = '#ddd';
        b.style.color = '#333';
    });
    const btn = document.querySelector(`.preset-btn[data-preset="${preset}"]`);
    if (btn) {
        btn.style.background = '#302b63';
        btn.style.borderColor = '#302b63';
        btn.style.color = '#fff';
    }

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

// ===== 查询 =====
async function fetchData() {
    let code = document.getElementById('stockInput').value.trim();
    if (selectedTsCode) code = selectedTsCode;
    if (!code) { showError('请输入股票名称或代码'); return; }

    const { start, end } = getDateRange();
    if (start > end) { showError('开始日期不能晚于结束日期'); return; }

    document.getElementById('errorBox').style.display = 'none';
    document.getElementById('content').style.display = 'none';
    document.getElementById('loading').style.display = 'block';
    document.getElementById('subtitle').textContent = '正在查询 ' + code + ' (' + start + ' ~ ' + end + ') ...';

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
document.querySelectorAll('.preset-btn').forEach(btn => {
    btn.addEventListener('click', () => applyPreset(btn.dataset.preset));
});
initDateSelects();
// 默认高亮"近1年"
const defBtn = document.querySelector('.preset-btn[data-preset="1y"]');
if (defBtn) {
    defBtn.style.background = '#302b63';
    defBtn.style.borderColor = '#302b63';
    defBtn.style.color = '#fff';
}
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
