#!/usr/bin/env python3
"""
Task 3 双均线策略看板后端
==========================
基于 Tushare Pro API，为 Task 3 提供股票搜索、日线数据、复权处理和
双均线策略回测（金叉/死叉信号、净值曲线、回撤曲线、绩效指标）、
多参数对比与多股票对比服务。

用法：
  1. 设置 TUSHARE_TOKEN 环境变量（或在下方修改 TOKEN 变量）
  2. python task3_backend.py
  3. 浏览器打开 http://localhost:5002
"""

import os
import json
import re
from datetime import datetime, timedelta

import tushare as ts
import pandas as pd
import numpy as np
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
_CACHE_FILE = os.path.join(os.path.dirname(__file__), ".task3_stock_cache.json")

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
        base = factors.iloc[-1]
    else:
        base = factors.iloc[0]

    ratio = factors / base
    price_cols = ["open", "high", "low", "close", "pre_close"]
    for col in price_cols:
        if col in df.columns:
            df[col] = (df[col].astype(float) * ratio).round(2)

    df["pct_chg"] = df["close"].pct_change() * 100
    df["pct_chg"] = df["pct_chg"].round(2)
    df["change"] = (df["close"] - df["pre_close"]).round(2)

    return df


def to_list(s):
    """将 pandas Series 转为 list，NaN 转为 None。"""
    out = []
    for v in s.tolist():
        if pd.isna(v):
            out.append(None)
        else:
            out.append(float(v))
    return out


def backtest_dual_ma(close: pd.Series, short_win: int, long_win: int, risk_free: float = 0.02):
    """
    双均线策略回测核心。
    返回信号序列、净值序列、回撤序列以及绩效指标。
    """
    n = len(close)
    ma_short = close.rolling(window=short_win).mean().values
    ma_long = close.rolling(window=long_win).mean().values

    signal = np.zeros(n, dtype=int)
    for i in range(1, n):
        if np.isnan(ma_short[i]) or np.isnan(ma_long[i]):
            continue
        if np.isnan(ma_short[i-1]) or np.isnan(ma_long[i-1]):
            continue
        if ma_short[i-1] <= ma_long[i-1] and ma_short[i] > ma_long[i]:
            signal[i] = 1   # 金叉买入
        elif ma_short[i-1] >= ma_long[i-1] and ma_short[i] < ma_long[i]:
            signal[i] = -1  # 死叉卖出

    position = 0
    equity = np.ones(n)
    entry_idx = 0
    for i in range(1, n):
        if signal[i] == 1 and position == 0:
            position = 1
            entry_idx = i
        elif signal[i] == -1 and position == 1:
            position = 0
            equity[i:] = equity[i:] * (close.iloc[i] / close.iloc[entry_idx])

    # 最后仍持仓，按最后一天收盘价结算
    if position == 1 and entry_idx < n - 1:
        equity[-1] = equity[-1] * (close.iloc[-1] / close.iloc[entry_idx])
    elif position == 1:
        equity[-1] = equity[-1] * (close.iloc[-1] / close.iloc[entry_idx])

    rolling_max = np.maximum.accumulate(equity)
    drawdown = (equity - rolling_max) / rolling_max
    mdd = float(np.min(drawdown))

    total_return = float(equity[-1] - 1.0)

    daily_ret = np.diff(equity) / equity[:-1]
    if len(daily_ret) > 0 and np.std(daily_ret, ddof=1) > 0:
        ann_ret = float(np.mean(daily_ret) * 252)
        ann_vol = float(np.std(daily_ret, ddof=1) * np.sqrt(252))
        sharpe = float((ann_ret - risk_free) / ann_vol)
    else:
        ann_ret = 0.0
        ann_vol = 0.0
        sharpe = 0.0

    n_buy = int(np.sum(signal == 1))
    n_sell = int(np.sum(signal == -1))

    return {
        "ma_short": to_list(pd.Series(ma_short)),
        "ma_long": to_list(pd.Series(ma_long)),
        "signal": signal.tolist(),
        "equity": equity.tolist(),
        "drawdown": drawdown.tolist(),
        "metrics": {
            "cum_return": round(total_return * 100, 2),
            "mdd": round(mdd * 100, 2),
            "ann_return": round(ann_ret * 100, 2),
            "ann_vol": round(ann_vol * 100, 2),
            "sharpe": round(sharpe, 4),
            "n_buy": n_buy,
            "n_sell": n_sell,
            "n_trade": n_buy + n_sell,
        }
    }


def calc_backtest(df: pd.DataFrame, short_win: int = 5, long_win: int = 15,
                  risk_free: float = 0.02) -> dict:
    """为单只股票计算双均线回测结果并打包前端所需数据。"""
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    vol = df["vol"].astype(float)
    dates = df["trade_date"].tolist()

    bt = backtest_dual_ma(close, short_win, long_win, risk_free)

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
        "shortWin": short_win,
        "longWin": long_win,
        "maShort": bt["ma_short"],
        "maLong": bt["ma_long"],
        "signal": bt["signal"],
        "equity": bt["equity"],
        "drawdown": bt["drawdown"],
        "metrics": bt["metrics"],
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


def calc_multi_param(df: pd.DataFrame, param_sets: list[tuple[int, int]],
                     risk_free: float = 0.02) -> list[dict]:
    """多组均线参数回测对比。"""
    close = df["close"].astype(float)
    results = []
    for sw, lw in param_sets:
        bt = backtest_dual_ma(close, sw, lw, risk_free)
        results.append({
            "param": f"MA{sw}/{lw}",
            "shortWin": sw,
            "longWin": lw,
            "cumReturn": bt["metrics"]["cum_return"],
            "mdd": bt["metrics"]["mdd"],
            "annReturn": bt["metrics"]["ann_return"],
            "annVol": bt["metrics"]["ann_vol"],
            "sharpe": bt["metrics"]["sharpe"],
            "nTrade": bt["metrics"]["n_trade"],
            "equity": bt["equity"],
        })
    return results


def calc_multi_stock(ts_codes: list[str], start_date: str, end_date: str,
                     short_win: int, long_win: int, adj_type: str,
                     risk_free: float = 0.02) -> list[dict]:
    """多只股票在相同均线参数下回测对比。"""
    results = []
    for code in ts_codes:
        try:
            resolved = resolve_tscode(code)
            df = fetch_daily(resolved, start_date, end_date)
            df.attrs["adj_type"] = adj_type
            df = apply_adjustment(df, adj_type)
            close = df["close"].astype(float)
            bt = backtest_dual_ma(close, short_win, long_win, risk_free)
            results.append({
                "tsCode": df.iloc[0]["ts_code"],
                "name": df.iloc[0]["ts_code"].split('.')[0],
                "cumReturn": bt["metrics"]["cum_return"],
                "mdd": bt["metrics"]["mdd"],
                "annReturn": bt["metrics"]["ann_return"],
                "annVol": bt["metrics"]["ann_vol"],
                "sharpe": bt["metrics"]["sharpe"],
                "nTrade": bt["metrics"]["n_trade"],
                "equity": bt["equity"],
                "dates": [d[:4] + "-" + d[4:6] + "-" + d[6:] for d in df["trade_date"].tolist()],
            })
        except Exception as e:
            results.append({
                "tsCode": code,
                "name": code,
                "error": str(e),
            })
    return results


# ===== 路由 =====
@app.route("/")
def index():
    """直接渲染 Task 3 看板页面。"""
    try:
        with open(os.path.join(os.path.dirname(__file__), "task3_dashboard.html"),
                  "r", encoding="utf-8") as f:
            html = f.read()
        return html
    except Exception as e:
        return f"<h1>Task 3 双均线策略看板</h1><p>加载页面失败: {e}</p><p>请确认 task3_dashboard.html 存在。</p>"


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


@app.route("/api/backtest")
def api_backtest():
    """
    双均线策略回测。
    参数:
      tscode: 股票代码或中文名
      start_date / end_date: YYYY-MM-DD（可选）
      adj: 复权方式 none | qfq | hfq（默认 qfq）
      short_win / long_win: 短/长均线周期（默认 5 / 15）
      risk_free: 无风险利率年化（默认 0.02）
    """
    tscode = request.args.get("tscode", "").strip()
    if not tscode:
        return jsonify({"error": "请提供股票代码"})

    try:
        adj_type = request.args.get("adj", "qfq").strip().lower()
        if adj_type not in ("none", "qfq", "hfq"):
            adj_type = "qfq"

        short_win = int(request.args.get("short_win", 5))
        long_win = int(request.args.get("long_win", 15))
        if short_win >= long_win:
            return jsonify({"error": "短期均线周期必须小于长期均线周期"})
        if short_win < 1 or long_win < 1:
            return jsonify({"error": "均线周期必须为正整数"})

        risk_free = float(request.args.get("risk_free", 0.02))

        resolved = resolve_tscode(tscode)
        df = fetch_daily(
            resolved,
            start_date=request.args.get("start_date") or None,
            end_date=request.args.get("end_date") or None,
        )
        df.attrs["adj_type"] = adj_type
        df = apply_adjustment(df, adj_type)
        result = calc_backtest(df, short_win, long_win, risk_free)
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)})


@app.route("/api/compare_params")
def api_compare_params():
    """
    多组均线参数回测对比。
    参数同 /api/backtest，额外支持 params 参数如 params=5/15,10/30,20/60
    """
    tscode = request.args.get("tscode", "").strip()
    if not tscode:
        return jsonify({"error": "请提供股票代码"})

    try:
        adj_type = request.args.get("adj", "qfq").strip().lower()
        if adj_type not in ("none", "qfq", "hfq"):
            adj_type = "qfq"

        params_raw = request.args.get("params", "5/15,10/30,20/60,5/20,10/20,10/60")
        param_sets = []
        for part in params_raw.split(","):
            part = part.strip()
            if "/" not in part:
                continue
            sw, lw = part.split("/")
            sw, lw = int(sw.strip()), int(lw.strip())
            if sw < 1 or lw < 1 or sw >= lw:
                continue
            param_sets.append((sw, lw))

        if not param_sets:
            param_sets = [(5, 15), (10, 30), (20, 60), (5, 20), (10, 20), (10, 60)]

        risk_free = float(request.args.get("risk_free", 0.02))

        resolved = resolve_tscode(tscode)
        df = fetch_daily(
            resolved,
            start_date=request.args.get("start_date") or None,
            end_date=request.args.get("end_date") or None,
        )
        df.attrs["adj_type"] = adj_type
        df = apply_adjustment(df, adj_type)

        results = calc_multi_param(df, param_sets, risk_free)
        return jsonify({
            "tsCode": df.iloc[0]["ts_code"],
            "dates": [d[:4] + "-" + d[4:6] + "-" + d[6:] for d in df["trade_date"].tolist()],
            "results": results,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)})


@app.route("/api/compare_stocks")
def api_compare_stocks():
    """
    多只股票在相同均线参数下回测对比。
    参数:
      tscodes: 逗号分隔的股票代码
      start_date / end_date / adj / short_win / long_win
    """
    tscodes = request.args.get("tscodes", "").strip()
    if not tscodes:
        return jsonify({"error": "请提供股票代码"})

    try:
        codes = [c.strip() for c in tscodes.split(",") if c.strip()]
        if len(codes) < 1:
            return jsonify({"error": "请至少提供一只股票代码"})

        adj_type = request.args.get("adj", "qfq").strip().lower()
        if adj_type not in ("none", "qfq", "hfq"):
            adj_type = "qfq"

        short_win = int(request.args.get("short_win", 10))
        long_win = int(request.args.get("long_win", 30))
        if short_win >= long_win:
            return jsonify({"error": "短期均线周期必须小于长期均线周期"})

        risk_free = float(request.args.get("risk_free", 0.02))

        results = calc_multi_stock(
            codes,
            request.args.get("start_date") or None,
            request.args.get("end_date") or None,
            short_win, long_win, adj_type, risk_free,
        )
        return jsonify({
            "param": f"MA{short_win}/{long_win}",
            "shortWin": short_win,
            "longWin": long_win,
            "results": results,
        })
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
    print("📊 启动 Task 3 双均线策略看板服务器...")
    print("   浏览器打开: http://localhost:5002")
    print("   支持：复权选择，双均线参数自定义，回测指标，多参数/多股票对比")
    app.run(host="0.0.0.0", port=5002, debug=False)
