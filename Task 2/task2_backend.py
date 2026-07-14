#!/usr/bin/env python3
"""
Task 2 技术指标看板后端
======================
基于 Tushare Pro API，为 Task 2 提供股票搜索、日线数据、复权处理和
技术指标（RSI / MACD / 布林带 / KDJ / MA）计算服务。

用法：
  1. 设置 TUSHARE_TOKEN 环境变量（或在下方修改 TOKEN 变量）
  2. python task2_backend.py
  3. 浏览器打开 http://localhost:5001
"""

import os
import json
import re
from datetime import datetime, timedelta

import tushare as ts
import pandas as pd
from flask import Flask, request, jsonify

# ===== 配置 =====
TOKEN = os.environ.get(
    "TUSHARE_TOKEN",
    "6f9eca8f7a38eda0bdd0ebbd1c9063498b26a7ee96c374eaba4167eb",
)
ts.set_token(TOKEN)
pro = ts.pro_api()

# ===== Flask =====
app = Flask(__name__)


# ===== 允许跨域 =====
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
_stock_cache = None
_STOCK_CACHE_TIME = 3600
_last_cache_time = 0
_CACHE_FILE = os.path.join(os.path.dirname(__file__), ".task2_stock_cache.json")

# 当 Tushare stock_basic 接口受限时的兜底常用股票列表
FALLBACK_STOCKS = [
    {"code":"000001","tsCode":"000001.SZ","name":"平安银行","market":"主板"},
    {"code":"000002","tsCode":"000002.SZ","name":"万科A","market":"主板"},
    {"code":"000333","tsCode":"000333.SZ","name":"美的集团","market":"主板"},
    {"code":"000651","tsCode":"000651.SZ","name":"格力电器","market":"主板"},
    {"code":"000858","tsCode":"000858.SZ","name":"五粮液","market":"主板"},
    {"code":"002230","tsCode":"002230.SZ","name":"科大讯飞","market":"主板"},
    {"code":"002415","tsCode":"002415.SZ","name":"海康威视","market":"主板"},
    {"code":"002475","tsCode":"002475.SZ","name":"立讯精密","market":"主板"},
    {"code":"002714","tsCode":"002714.SZ","name":"牧原股份","market":"主板"},
    {"code":"300059","tsCode":"300059.SZ","name":"东方财富","market":"创业板"},
    {"code":"300124","tsCode":"300124.SZ","name":"汇川技术","market":"创业板"},
    {"code":"300274","tsCode":"300274.SZ","name":"阳光电源","market":"创业板"},
    {"code":"300308","tsCode":"300308.SZ","name":"中际旭创","market":"创业板"},
    {"code":"300750","tsCode":"300750.SZ","name":"宁德时代","market":"创业板"},
    {"code":"300760","tsCode":"300760.SZ","name":"迈瑞医疗","market":"创业板"},
    {"code":"600000","tsCode":"600000.SH","name":"浦发银行","market":"主板"},
    {"code":"600028","tsCode":"600028.SH","name":"中国石化","market":"主板"},
    {"code":"600030","tsCode":"600030.SH","name":"中信证券","market":"主板"},
    {"code":"600031","tsCode":"600031.SH","name":"三一重工","market":"主板"},
    {"code":"600036","tsCode":"600036.SH","name":"招商银行","market":"主板"},
    {"code":"600048","tsCode":"600048.SH","name":"保利发展","market":"主板"},
    {"code":"600104","tsCode":"600104.SH","name":"上汽集团","market":"主板"},
    {"code":"600150","tsCode":"600150.SH","name":"中国船舶","market":"主板"},
    {"code":"600276","tsCode":"600276.SH","name":"恒瑞医药","market":"主板"},
    {"code":"600309","tsCode":"600309.SH","name":"万华化学","market":"主板"},
    {"code":"600519","tsCode":"600519.SH","name":"贵州茅台","market":"主板"},
    {"code":"600585","tsCode":"600585.SH","name":"海螺水泥","market":"主板"},
    {"code":"600690","tsCode":"600690.SH","name":"海尔智家","market":"主板"},
    {"code":"600809","tsCode":"600809.SH","name":"山西汾酒","market":"主板"},
    {"code":"600887","tsCode":"600887.SH","name":"伊利股份","market":"主板"},
    {"code":"600900","tsCode":"600900.SH","name":"长江电力","market":"主板"},
    {"code":"601012","tsCode":"601012.SH","name":"隆基绿能","market":"主板"},
    {"code":"601088","tsCode":"601088.SH","name":"中国神华","market":"主板"},
    {"code":"601127","tsCode":"601127.SH","name":"赛力斯","market":"主板"},
    {"code":"601138","tsCode":"601138.SH","name":"工业富联","market":"主板"},
    {"code":"601166","tsCode":"601166.SH","name":"兴业银行","market":"主板"},
    {"code":"601318","tsCode":"601318.SH","name":"中国平安","market":"主板"},
    {"code":"601328","tsCode":"601328.SH","name":"交通银行","market":"主板"},
    {"code":"601398","tsCode":"601398.SH","name":"工商银行","market":"主板"},
    {"code":"601628","tsCode":"601628.SH","name":"中国人寿","market":"主板"},
    {"code":"601633","tsCode":"601633.SH","name":"长城汽车","market":"主板"},
    {"code":"601668","tsCode":"601668.SH","name":"中国建筑","market":"主板"},
    {"code":"601688","tsCode":"601688.SH","name":"华泰证券","market":"主板"},
    {"code":"601728","tsCode":"601728.SH","name":"中国电信","market":"主板"},
    {"code":"601766","tsCode":"601766.SH","name":"中国中车","market":"主板"},
    {"code":"601857","tsCode":"601857.SH","name":"中国石油","market":"主板"},
    {"code":"601899","tsCode":"601899.SH","name":"紫金矿业","market":"主板"},
    {"code":"601919","tsCode":"601919.SH","name":"中远海控","market":"主板"},
    {"code":"601939","tsCode":"601939.SH","name":"建设银行","market":"主板"},
    {"code":"601985","tsCode":"601985.SH","name":"中国核电","market":"主板"},
    {"code":"601988","tsCode":"601988.SH","name":"中国银行","market":"主板"},
    {"code":"603259","tsCode":"603259.SH","name":"药明康德","market":"主板"},
    {"code":"603288","tsCode":"603288.SH","name":"海天味业","market":"主板"},
    {"code":"603501","tsCode":"603501.SH","name":"韦尔股份","market":"主板"},
    {"code":"688012","tsCode":"688012.SH","name":"中微公司","market":"科创板"},
    {"code":"688041","tsCode":"688041.SH","name":"海光信息","market":"科创板"},
    {"code":"688111","tsCode":"688111.SH","name":"金山办公","market":"科创板"},
    {"code":"688256","tsCode":"688256.SH","name":"寒武纪","market":"科创板"},
    {"code":"688271","tsCode":"688271.SH","name":"联影医疗","market":"科创板"},
    {"code":"688981","tsCode":"688981.SH","name":"中芯国际","market":"科创板"},
]


def load_stock_list() -> list[dict]:
    """加载 A 股基础信息列表，供搜索建议使用。"""
    global _stock_cache, _last_cache_time
    now = datetime.now().timestamp()

    if _stock_cache is not None and (now - _last_cache_time) < _STOCK_CACHE_TIME:
        return _stock_cache

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

    stocks = []
    try:
        df = pro.stock_basic(
            fields=["ts_code", "symbol", "name", "market", "list_status"]
        )
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                ts_code = row["ts_code"]
                sym = row["symbol"]
                name = row["name"]
                market = row["market"]
                stocks.append({
                    "code": sym,
                    "tsCode": ts_code,
                    "name": name,
                    "market": market,
                    "searchKey": f"{name} {sym} {ts_code}",
                })
    except Exception as e:
        print(f"[警告] 加载股票列表失败: {e}")

    if not stocks:
        print("[信息] 使用内置兜底股票列表")
        stocks = []
        for s in FALLBACK_STOCKS:
            item = dict(s)
            item["searchKey"] = f"{item['name']} {item['code']} {item['tsCode']}"
            stocks.append(item)

    stocks.sort(key=lambda x: x["code"])
    _stock_cache = stocks
    _last_cache_time = now

    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(stocks, f, ensure_ascii=False)
        print(f"[信息] 已保存 {len(stocks)} 只股票到本地缓存")
    except Exception as e:
        print(f"[警告] 写入本地缓存失败: {e}")

    return stocks


def resolve_tscode(query: str) -> str:
    """将用户输入解析为 Tushare 标准 ts_code。"""
    q = query.strip()
    if not q:
        return q

    if re.match(r"^\d{6}\.(SH|SZ|BJ)$", q.upper()):
        return q.upper()

    m = re.match(r"^([a-zA-Z]{2})?(\d{6})([a-zA-Z]{2})?$", q)
    if m:
        code = m.group(2)
        prefix = (m.group(1) or m.group(3) or "").upper()
        suffix_map = {"SH": ".SH", "SZ": ".SZ", "BJ": ".BJ"}
        if prefix in suffix_map:
            return code + suffix_map[prefix]
        stocks = load_stock_list()
        for s in stocks:
            if s["code"] == code:
                return s["tsCode"]
        return code + ".SH"

    if re.match(r"^(hk|HK|Hk)\d{5}$", q):
        return q

    stocks = load_stock_list()
    matched = [s for s in stocks if q in s["name"] or q in s["code"]]
    if matched:
        exact = [s for s in matched if s["name"] == q]
        if exact:
            return exact[0]["tsCode"]
        return matched[0]["tsCode"]

    return q


def norm_date(d):
    if d is None:
        return None
    d = d.strip().replace("-", "").replace("/", "")
    if len(d) != 8 or not d.isdigit():
        raise ValueError(f"日期格式错误，应为 YYYY-MM-DD 或 YYYYMMDD: {d}")
    return d


def fetch_daily(ts_code: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """从 Tushare 获取日线数据（含复权因子）。"""
    start = norm_date(start_date) or (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
    end = norm_date(end_date) or datetime.now().strftime("%Y%m%d")

    df = pro.daily(
        ts_code=ts_code, start_date=start, end_date=end,
        fields=["ts_code", "trade_date", "open", "high", "low", "close",
                "pre_close", "change", "pct_chg", "vol", "amount"],
    )
    if df is None or df.empty:
        raise ValueError(f"未获取到 {ts_code} 在 {start}~{end} 之间的数据")

    # 获取复权因子
    try:
        adj_df = pro.adj_factor(ts_code=ts_code, start_date=start, end_date=end,
                                fields=["ts_code", "trade_date", "adj_factor"])
        if adj_df is not None and not adj_df.empty:
            df = df.merge(adj_df[["trade_date", "adj_factor"]], on="trade_date", how="left")
            df["adj_factor"] = df["adj_factor"].astype(float)
        else:
            df["adj_factor"] = 1.0
    except Exception as e:
        print(f"[警告] 获取复权因子失败: {e}")
        df["adj_factor"] = 1.0

    df = df.sort_values("trade_date").reset_index(drop=True)
    return df


def apply_adjustment(df: pd.DataFrame, adj_type: str) -> pd.DataFrame:
    """
    应用复权处理。
    adj_type: none | qfq | hfq
    """
    if adj_type not in ("qfq", "hfq") or "adj_factor" not in df.columns:
        return df

    df = df.copy()
    factors = df["adj_factor"].astype(float)

    if adj_type == "qfq":
        base = factors.iloc[-1]  # 以最新交易日为基准
    else:  # hfq
        base = factors.iloc[0]  # 以最早交易日为基准

    ratio = factors / base
    price_cols = ["open", "high", "low", "close", "pre_close"]
    for col in price_cols:
        if col in df.columns:
            df[col] = (df[col].astype(float) * ratio).round(2)

    # 涨跌幅基于复权后的收盘价重新计算
    df["pct_chg"] = df["close"].pct_change() * 100
    df["pct_chg"] = df["pct_chg"].round(2)
    df["change"] = (df["close"] - df["pre_close"]).round(2)

    return df


def calc_diagnosis(df: pd.DataFrame) -> dict:
    """
    数据诊断：缺失值检查 + 描述性统计量。
    返回:
      - missing: 各列的缺失值数量与占比
      - describe: 数值列的描述性统计（count/mean/std/min/25%/50%/75%/max）
      - outliers: 基于 3σ 的异常值检测
      - date_range: 数据日期范围与连续性
    """
    # 缺失值检查
    missing = {}
    total = len(df)
    for col in df.columns:
        n_missing = int(df[col].isna().sum())
        if n_missing > 0:
            missing[col] = {
                "count": n_missing,
                "pct": round(n_missing / total * 100, 2),
            }

    # 描述性统计（只对数值列）
    numeric_cols = [c for c in ["open", "high", "low", "close", "vol", "amount", "pct_chg", "change"] if c in df.columns]
    describe = {}
    for col in numeric_cols:
        s = df[col].astype(float)
        describe[col] = {
            "count": int(s.count()),
            "mean": round(float(s.mean()), 4),
            "std": round(float(s.std()), 4),
            "min": round(float(s.min()), 4),
            "q25": round(float(s.quantile(0.25)), 4),
            "q50": round(float(s.quantile(0.50)), 4),
            "q75": round(float(s.quantile(0.75)), 4),
            "max": round(float(s.max()), 4),
        }

    # 异常值检测（3σ 准则）
    outliers = {}
    for col in ["open", "high", "low", "close", "vol", "pct_chg"]:
        if col not in df.columns:
            continue
        s = df[col].astype(float)
        mean = s.mean()
        std = s.std()
        if std == 0 or pd.isna(std):
            continue
        upper = mean + 3 * std
        lower = mean - 3 * std
        n_out = int(((s > upper) | (s < lower)).sum())
        if n_out > 0:
            outliers[col] = {
                "count": n_out,
                "pct": round(n_out / total * 100, 2),
                "upper": round(float(upper), 4),
                "lower": round(float(lower), 4),
            }

    # 日期连续性
    dates = pd.to_datetime(df["trade_date"], format="%Y%m%d").sort_values()
    if len(dates) >= 2:
        diffs = dates.diff().dropna()
        # 正常 A 股交易日间隔 = 1, 2, 3 天（跨周末 / 节假日）
        normal_gaps = int((diffs.dt.days <= 3).sum())
        abnormal_gaps = int((diffs.dt.days > 3).sum())
        max_gap = int(diffs.dt.days.max())
    else:
        normal_gaps = abnormal_gaps = max_gap = 0

    return {
        "missing": missing,
        "missingTotal": int(df.isna().any(axis=1).sum()),
        "describe": describe,
        "outliers": outliers,
        "outliersTotal": sum(v["count"] for v in outliers.values()),
        "dateRange": {
            "start": str(dates.iloc[0])[:10] if len(dates) > 0 else None,
            "end": str(dates.iloc[-1])[:10] if len(dates) > 0 else None,
            "days": int((dates.iloc[-1] - dates.iloc[0]).days) if len(dates) >= 2 else 0,
            "tradingDays": int(len(dates)),
            "normalGaps": normal_gaps,
            "abnormalGaps": abnormal_gaps,
            "maxGap": max_gap,
        },
    }


def calc_indicators(df: pd.DataFrame, rsi_period: int = 14,
                    macd_fast: int = 12, macd_slow: int = 26, macd_signal: int = 9,
                    bb_period: int = 20, bb_k: float = 2.0,
                    kdj_n: int = 9, kdj_m1: int = 3, kdj_m2: int = 3) -> dict:
    """计算 RSI / MACD / 布林带 / KDJ / MA 技术指标。"""
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    vol = df["vol"].astype(float)
    n = len(close)
    dates = df["trade_date"].tolist()

    # MA
    ma5 = close.rolling(5).mean().round(2)
    ma10 = close.rolling(10).mean().round(2)
    ma20 = close.rolling(20).mean().round(2)
    ma60 = close.rolling(60).mean().round(2)

    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1/rsi_period, adjust=False, min_periods=rsi_period).mean()
    avg_loss = loss.ewm(alpha=1/rsi_period, adjust=False, min_periods=rsi_period).mean()
    rs = avg_gain / avg_loss
    rsi = (100 - 100 / (1 + rs)).round(2)

    # MACD
    ema_fast = close.ewm(span=macd_fast, adjust=False).mean()
    ema_slow = close.ewm(span=macd_slow, adjust=False).mean()
    dif = (ema_fast - ema_slow).round(4)
    dea = dif.ewm(span=macd_signal, adjust=False).mean().round(4)
    macd_hist = ((dif - dea) * 2).round(4)

    # 布林带
    boll_mid = close.rolling(bb_period).mean().round(2)
    std = close.rolling(bb_period).std(ddof=0).round(2)
    boll_upper = (boll_mid + bb_k * std).round(2)
    boll_lower = (boll_mid - bb_k * std).round(2)

    # KDJ
    low_n = low.rolling(kdj_n).min()
    high_n = high.rolling(kdj_n).max()
    rsv = ((close - low_n) / (high_n - low_n) * 100).round(2)
    k_line = rsv.ewm(alpha=1/kdj_m1, adjust=False).mean().round(2)
    d_line = k_line.ewm(alpha=1/kdj_m2, adjust=False).mean().round(2)
    j_line = (3 * k_line - 2 * d_line).round(2)

    def to_list(s):
        out = []
        for v in s.tolist():
            if pd.isna(v):
                out.append(None)
            else:
                out.append(float(v))
        return out

    first_close = close.iloc[0]
    last_close = close.iloc[-1]

    return {
        "tsCode": df.iloc[0]["ts_code"],
        "adjType": df.attrs.get("adj_type", "none"),
        "dates": [d[:4] + "-" + d[4:6] + "-" + d[6:] for d in dates],
        "rawDates": dates,
        "kline": [[round(float(r["open"]), 2), round(float(r["close"]), 2),
                   round(float(r["low"]), 2), round(float(r["high"]), 2)]
                  for _, r in df.iterrows()],
        "vol": to_list(vol),
        "pct": to_list(df["pct_chg"]),
        "ma": {
            "ma5": to_list(ma5), "ma10": to_list(ma10),
            "ma20": to_list(ma20), "ma60": to_list(ma60),
        },
        "rsi": {
            "period": rsi_period,
            "values": to_list(rsi),
        },
        "macd": {
            "fast": macd_fast, "slow": macd_slow, "signal": macd_signal,
            "dif": to_list(dif), "dea": to_list(dea), "hist": to_list(macd_hist),
        },
        "boll": {
            "period": bb_period, "k": bb_k,
            "upper": to_list(boll_upper), "mid": to_list(boll_mid), "lower": to_list(boll_lower),
        },
        "kdj": {
            "n": kdj_n, "m1": kdj_m1, "m2": kdj_m2,
            "k": to_list(k_line), "d": to_list(d_line), "j": to_list(j_line),
        },
        "stats": {
            "start": dates[0][:4] + "-" + dates[0][4:6] + "-" + dates[0][6:],
            "end": dates[-1][:4] + "-" + dates[-1][4:6] + "-" + dates[-1][6:],
            "lastClose": round(float(last_close), 2),
            "highMax": round(float(high.max()), 2),
            "lowMin": round(float(low.min()), 2),
            "change": round(float(last_close - first_close), 2),
            "changePct": round(float((last_close - first_close) / first_close * 100), 2),
            "totalVol": round(float(vol.sum() / 10000), 2),
            "days": len(df),
        },
    }


# ===== 路由 =====
@app.route("/")
def index():
    """直接渲染 Task 2 看板页面。"""
    try:
        with open(os.path.join(os.path.dirname(__file__), "dashboard.html"),
                  "r", encoding="utf-8") as f:
            html = f.read()
        return html
    except Exception as e:
        return f"<h1>Task 2 看板</h1><p>加载页面失败: {e}</p><p>请确认 dashboard.html 存在。</p>"


@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    if not q or len(q) < 1:
        return jsonify({"stocks": []})
    stocks = load_stock_list()
    q_lower = q.lower()
    matched = [s for s in stocks if q_lower in s["searchKey"].lower()]

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


@app.route("/api/diagnosis")
def api_diagnosis():
    """
    数据诊断：缺失值 + 描述性统计 + 异常值检测。
    参数同 /api/indicators。
    """
    tscode = request.args.get("tscode", "").strip()
    if not tscode:
        return jsonify({"error": "请提供股票代码"})

    try:
        adj_type = request.args.get("adj", "qfq").strip().lower()
        if adj_type not in ("none", "qfq", "hfq"):
            adj_type = "qfq"

        resolved = resolve_tscode(tscode)
        df = fetch_daily(
            resolved,
            start_date=request.args.get("start_date") or None,
            end_date=request.args.get("end_date") or None,
        )
        df.attrs["adj_type"] = adj_type
        df = apply_adjustment(df, adj_type)

        diag = calc_diagnosis(df)
        diag["tsCode"] = df.iloc[0]["ts_code"]
        return jsonify(diag)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)})


@app.route("/api/indicators")
def api_indicators():
    """
    返回复权后的 K 线 + 技术指标。
    参数:
      tscode: 股票代码或中文名
      start_date / end_date: YYYY-MM-DD（可选）
      adj: 复权方式 none | qfq | hfq（默认 qfq）
      rsi_period, macd_fast, macd_slow, macd_signal, bb_period, bb_k,
      kdj_n, kdj_m1, kdj_m2: 指标参数
    """
    tscode = request.args.get("tscode", "").strip()
    if not tscode:
        return jsonify({"error": "请提供股票代码"})

    try:
        adj_type = request.args.get("adj", "qfq").strip().lower()
        if adj_type not in ("none", "qfq", "hfq"):
            adj_type = "qfq"

        rsi_period = int(request.args.get("rsi_period", 14))
        macd_fast = int(request.args.get("macd_fast", 12))
        macd_slow = int(request.args.get("macd_slow", 26))
        macd_signal = int(request.args.get("macd_signal", 9))
        bb_period = int(request.args.get("bb_period", 20))
        bb_k = float(request.args.get("bb_k", 2.0))
        kdj_n = int(request.args.get("kdj_n", 9))
        kdj_m1 = int(request.args.get("kdj_m1", 3))
        kdj_m2 = int(request.args.get("kdj_m2", 3))

        resolved = resolve_tscode(tscode)
        df = fetch_daily(
            resolved,
            start_date=request.args.get("start_date") or None,
            end_date=request.args.get("end_date") or None,
        )
        df.attrs["adj_type"] = adj_type
        df = apply_adjustment(df, adj_type)
        ind = calc_indicators(
            df, rsi_period=rsi_period, macd_fast=macd_fast,
            macd_slow=macd_slow, macd_signal=macd_signal,
            bb_period=bb_period, bb_k=bb_k,
            kdj_n=kdj_n, kdj_m1=kdj_m1, kdj_m2=kdj_m2,
        )
        return jsonify(ind)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)})


# ===== 启动 =====
if __name__ == "__main__":
    print("🚀 正在预加载股票基础信息...")
    try:
        count = len(load_stock_list())
        print(f"   ✅ 已加载 {count} 只股票")
    except Exception as e:
        print(f"   ⚠️ 加载股票列表失败（不影响查询，仅搜索建议不可用）: {e}")
    print("📊 启动 Task 2 技术指标看板服务器...")
    print("   浏览器打开: http://localhost:5001")
    print("   支持：不复权 / 前复权 / 后复权，RSI / MACD / 布林带 / KDJ")
    app.run(host="0.0.0.0", port=5001, debug=False)
