#!/usr/bin/env python3
"""
Task 4 海龟交易策略看板后端
==========================
基于 Tushare Pro API，为 Task 4 提供股票搜索、日线数据、复权处理和
海龟策略回测（唐奇安通道突破 + ATR 动态仓位 + 2N 止损）、净值曲线、
回撤曲线、绩效指标、多参数对比与多股票对比服务。

用法：
  1. 设置 TUSHARE_TOKEN 环境变量（或在下方修改 TOKEN 变量）
  2. python task4_backend.py
  3. 浏览器打开 http://localhost:5004
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
_CACHE_FILE = os.path.join(os.path.dirname(__file__), ".task4_stock_cache.json")

# 当 Tushare stock_basic 接口受限时的兜底常用股票列表
FALLBACK_STOCKS = [
    {"code": "000001", "tsCode": "000001.SZ", "name": "平安银行", "market": "主板"},
    {"code": "000002", "tsCode": "000002.SZ", "name": "万科A", "market": "主板"},
    {"code": "000333", "tsCode": "000333.SZ", "name": "美的集团", "market": "主板"},
    {"code": "000651", "tsCode": "000651.SZ", "name": "格力电器", "market": "主板"},
    {"code": "000858", "tsCode": "000858.SZ", "name": "五粮液", "market": "主板"},
    {"code": "002230", "tsCode": "002230.SZ", "name": "科大讯飞", "market": "主板"},
    {"code": "002415", "tsCode": "002415.SZ", "name": "海康威视", "market": "主板"},
    {"code": "002475", "tsCode": "002475.SZ", "name": "立讯精密", "market": "主板"},
    {"code": "002714", "tsCode": "002714.SZ", "name": "牧原股份", "market": "主板"},
    {"code": "300059", "tsCode": "300059.SZ", "name": "东方财富", "market": "创业板"},
    {"code": "300124", "tsCode": "300124.SZ", "name": "汇川技术", "market": "创业板"},
    {"code": "300274", "tsCode": "300274.SZ", "name": "阳光电源", "market": "创业板"},
    {"code": "300308", "tsCode": "300308.SZ", "name": "中际旭创", "market": "创业板"},
    {"code": "300750", "tsCode": "300750.SZ", "name": "宁德时代", "market": "创业板"},
    {"code": "300760", "tsCode": "300760.SZ", "name": "迈瑞医疗", "market": "创业板"},
    {"code": "600000", "tsCode": "600000.SH", "name": "浦发银行", "market": "主板"},
    {"code": "600028", "tsCode": "600028.SH", "name": "中国石化", "market": "主板"},
    {"code": "600030", "tsCode": "600030.SH", "name": "中信证券", "market": "主板"},
    {"code": "600031", "tsCode": "600031.SH", "name": "三一重工", "market": "主板"},
    {"code": "600036", "tsCode": "600036.SH", "name": "招商银行", "market": "主板"},
    {"code": "600048", "tsCode": "600048.SH", "name": "保利发展", "market": "主板"},
    {"code": "600104", "tsCode": "600104.SH", "name": "上汽集团", "market": "主板"},
    {"code": "600150", "tsCode": "600150.SH", "name": "中国船舶", "market": "主板"},
    {"code": "600276", "tsCode": "600276.SH", "name": "恒瑞医药", "market": "主板"},
    {"code": "600309", "tsCode": "600309.SH", "name": "万华化学", "market": "主板"},
    {"code": "600519", "tsCode": "600519.SH", "name": "贵州茅台", "market": "主板"},
    {"code": "600585", "tsCode": "600585.SH", "name": "海螺水泥", "market": "主板"},
    {"code": "600690", "tsCode": "600690.SH", "name": "海尔智家", "market": "主板"},
    {"code": "600809", "tsCode": "600809.SH", "name": "山西汾酒", "market": "主板"},
    {"code": "600887", "tsCode": "600887.SH", "name": "伊利股份", "market": "主板"},
    {"code": "600900", "tsCode": "600900.SH", "name": "长江电力", "market": "主板"},
    {"code": "601012", "tsCode": "601012.SH", "name": "隆基绿能", "market": "主板"},
    {"code": "601088", "tsCode": "601088.SH", "name": "中国神华", "market": "主板"},
    {"code": "601127", "tsCode": "601127.SH", "name": "赛力斯", "market": "主板"},
    {"code": "601138", "tsCode": "601138.SH", "name": "工业富联", "market": "主板"},
    {"code": "601166", "tsCode": "601166.SH", "name": "兴业银行", "market": "主板"},
    {"code": "601318", "tsCode": "601318.SH", "name": "中国平安", "market": "主板"},
    {"code": "601328", "tsCode": "601328.SH", "name": "交通银行", "market": "主板"},
    {"code": "601398", "tsCode": "601398.SH", "name": "工商银行", "market": "主板"},
    {"code": "601628", "tsCode": "601628.SH", "name": "中国人寿", "market": "主板"},
    {"code": "601633", "tsCode": "601633.SH", "name": "长城汽车", "market": "主板"},
    {"code": "601668", "tsCode": "601668.SH", "name": "中国建筑", "market": "主板"},
    {"code": "601688", "tsCode": "601688.SH", "name": "华泰证券", "market": "主板"},
    {"code": "601728", "tsCode": "601728.SH", "name": "中国电信", "market": "主板"},
    {"code": "601766", "tsCode": "601766.SH", "name": "中国中车", "market": "主板"},
    {"code": "601857", "tsCode": "601857.SH", "name": "中国石油", "market": "主板"},
    {"code": "601899", "tsCode": "601899.SH", "name": "紫金矿业", "market": "主板"},
    {"code": "601919", "tsCode": "601919.SH", "name": "中远海控", "market": "主板"},
    {"code": "601939", "tsCode": "601939.SH", "name": "建设银行", "market": "主板"},
    {"code": "601985", "tsCode": "601985.SH", "name": "中国核电", "market": "主板"},
    {"code": "601988", "tsCode": "601988.SH", "name": "中国银行", "market": "主板"},
    {"code": "603259", "tsCode": "603259.SH", "name": "药明康德", "market": "主板"},
    {"code": "603288", "tsCode": "603288.SH", "name": "海天味业", "market": "主板"},
    {"code": "603501", "tsCode": "603501.SH", "name": "韦尔股份", "market": "主板"},
    {"code": "688012", "tsCode": "688012.SH", "name": "中微公司", "market": "科创板"},
    {"code": "688041", "tsCode": "688041.SH", "name": "海光信息", "market": "科创板"},
    {"code": "688111", "tsCode": "688111.SH", "name": "金山办公", "market": "科创板"},
    {"code": "688256", "tsCode": "688256.SH", "name": "寒武纪", "market": "科创板"},
    {"code": "688271", "tsCode": "688271.SH", "name": "联影医疗", "market": "科创板"},
    {"code": "688981", "tsCode": "688981.SH", "name": "中芯国际", "market": "科创板"},
]


def load_stock_list() -> list:
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
    """应用复权处理。adj_type: none | qfq | hfq"""
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


def backtest_turtle(close: pd.Series, high: pd.Series, low: pd.Series,
                    period: int = 20, atr_period: int = 14,
                    stop_atr: float = 2.0, risk_ratio: float = 0.01,
                    initial_capital: float = 1_000_000,
                    risk_free: float = 0.02):
    """
    海龟策略回测核心。
    规则：
      - 买入：收盘价上穿 period 日最高价（唐奇安上轨）
      - 卖出：收盘价下穿 period 日最低价（唐奇安下轨）
      - 止损：entry - stop_atr * ATR
      - 仓位：账户权益 * risk_ratio / ATR（即每笔承担约 1% 账户风险）
    """
    n = len(close)
    c = close.values
    h = high.values
    l = low.values

    # 计算唐奇安通道
    upper = pd.Series(c).rolling(window=period).max().values
    lower = pd.Series(l).rolling(window=period).min().values

    # 计算 ATR (14)
    prev_c = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    atr = pd.Series(tr).rolling(window=atr_period).mean().values

    # 信号
    # 买入：今日收盘 > 昨日上轨 且 昨日收盘 <= 上轨前日
    buy_sig = np.zeros(n, dtype=int)
    sell_sig = np.zeros(n, dtype=int)
    for i in range(2, n):
        if np.isnan(upper[i - 1]) or np.isnan(upper[i - 2]):
            continue
        if c[i - 1] <= upper[i - 2] and c[i] > upper[i - 1]:
            buy_sig[i] = 1
        if c[i - 1] >= lower[i - 2] and c[i] < lower[i - 1]:
            sell_sig[i] = 1

    # 回测循环（带 ATR 仓位 + 止损）
    cash = initial_capital
    shares = 0
    entry_price = 0.0
    stop_price = 0.0

    equity = np.zeros(n)
    trade_log = []  # [(date_idx, type, price, shares, profit)]
    n_buy = 0
    n_sell = 0
    n_stop = 0
    win_count = 0
    loss_count = 0

    for i in range(n):
        close_i = c[i]
        atr_i = atr[i] if not np.isnan(atr[i]) else 0

        # 持仓期间：检查止损
        if shares > 0 and atr_i > 0:
            sp = entry_price - stop_atr * atr_i
            if close_i < sp:
                revenue = shares * close_i
                profit = revenue - shares * entry_price
                cash += revenue
                trade_log.append((i, "止损卖出", close_i, shares, profit))
                if profit >= 0:
                    win_count += 1
                else:
                    loss_count += 1
                shares = 0
                n_stop += 1

        # 买入信号
        if buy_sig[i] == 1 and shares == 0 and atr_i > 0:
            risk_amount = cash * risk_ratio
            unit = max(1, int(risk_amount / atr_i))  # 仓位 = 风险额 / ATR
            cost = unit * close_i
            if cost <= cash:
                shares = unit
                cash -= cost
                entry_price = close_i
                stop_price = entry_price - stop_atr * atr_i
                trade_log.append((i, "买入", close_i, unit, 0.0))
                n_buy += 1

        # 卖出信号（下穿下轨）
        elif sell_sig[i] == 1 and shares > 0:
            revenue = shares * close_i
            profit = revenue - shares * entry_price
            cash += revenue
            trade_log.append((i, "卖出", close_i, shares, profit))
            if profit >= 0:
                win_count += 1
            else:
                loss_count += 1
            shares = 0
            n_sell += 1

        equity[i] = cash + shares * close_i

    # 期末平仓
    if shares > 0:
        revenue = shares * c[-1]
        profit = revenue - shares * entry_price
        cash += revenue
        trade_log.append((n - 1, "期末平仓", c[-1], shares, profit))
        if profit >= 0:
            win_count += 1
        else:
            loss_count += 1
        shares = 0
        equity[-1] = cash

    # 归一化净值
    equity_norm = equity / initial_capital

    # 回撤
    rolling_max = np.maximum.accumulate(equity_norm)
    drawdown = (equity_norm - rolling_max) / rolling_max
    mdd = float(np.min(drawdown))

    total_return = float(equity_norm[-1] - 1.0)

    daily_ret = np.diff(equity_norm) / equity_norm[:-1]
    if len(daily_ret) > 0 and np.std(daily_ret, ddof=1) > 0:
        ann_ret = float(np.mean(daily_ret) * 252)
        ann_vol = float(np.std(daily_ret, ddof=1) * np.sqrt(252))
        sharpe = float((ann_ret - risk_free) / ann_vol)
    else:
        ann_ret = 0.0
        ann_vol = 0.0
        sharpe = 0.0

    n_trade = n_buy
    n_close = n_sell + n_stop + (1 if any(t[1] == "期末平仓" for t in trade_log) else 0)
    win_rate = win_count / n_close if n_close > 0 else 0

    return {
        "upper": upper.tolist(),
        "lower": lower.tolist(),
        "atr": atr.tolist(),
        "buy_signal": buy_sig.tolist(),
        "sell_signal": sell_sig.tolist(),
        "equity": equity_norm.tolist(),
        "drawdown": drawdown.tolist(),
        "trade_log": [
            {"idx": t[0], "type": t[1], "price": float(t[2]), "shares": int(t[3]), "profit": float(t[4])}
            for t in trade_log
        ],
        "metrics": {
            "cum_return": round(total_return * 100, 2),
            "mdd": round(mdd * 100, 2),
            "ann_return": round(ann_ret * 100, 2),
            "ann_vol": round(ann_vol * 100, 2),
            "sharpe": round(sharpe, 4),
            "n_buy": n_buy,
            "n_sell": n_sell,
            "n_stop": n_stop,
            "n_trade": n_trade,
            "n_close": n_close,
            "win_rate": round(win_rate * 100, 2),
        },
    }


def calc_backtest(df: pd.DataFrame, period: int = 20, atr_period: int = 14,
                  stop_atr: float = 2.0, risk_ratio: float = 0.01,
                  risk_free: float = 0.02) -> dict:
    """为单只股票计算海龟策略回测结果并打包前端所需数据。"""
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    vol = df["vol"].astype(float)
    dates = df["trade_date"].tolist()

    bt = backtest_turtle(close, high, low, period, atr_period, stop_atr,
                         risk_ratio, 1_000_000, risk_free)

    first_close = close.iloc[0]
    last_close = close.iloc[-1]

    # ATR/Upper/Lower 中的 NaN 转为 None
    atr_clean = [None if (isinstance(v, float) and np.isnan(v)) else (None if v is None else float(v))
                 for v in bt["atr"]]
    upper_clean = [None if (isinstance(v, float) and np.isnan(v)) else (None if v is None else float(v))
                   for v in bt["upper"]]
    lower_clean = [None if (isinstance(v, float) and np.isnan(v)) else (None if v is None else float(v))
                   for v in bt["lower"]]

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
        "period": period,
        "atrPeriod": atr_period,
        "stopAtr": stop_atr,
        "upper": upper_clean,
        "lower": lower_clean,
        "atr": atr_clean,
        "buySignal": bt["buy_signal"],
        "sellSignal": bt["sell_signal"],
        "equity": bt["equity"],
        "drawdown": bt["drawdown"],
        "tradeLog": bt["trade_log"],
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


def calc_multi_param(df: pd.DataFrame, periods: list,
                     atr_period: int = 14, stop_atr: float = 2.0,
                     risk_ratio: float = 0.01, risk_free: float = 0.02) -> list:
    """多组通道周期回测对比。"""
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    results = []
    for p in periods:
        bt = backtest_turtle(close, high, low, p, atr_period, stop_atr,
                             risk_ratio, 1_000_000, risk_free)
        results.append({
            "param": f"通道{p}日",
            "period": p,
            "cumReturn": bt["metrics"]["cum_return"],
            "mdd": bt["metrics"]["mdd"],
            "annReturn": bt["metrics"]["ann_return"],
            "annVol": bt["metrics"]["ann_vol"],
            "sharpe": bt["metrics"]["sharpe"],
            "nTrade": bt["metrics"]["n_trade"],
            "winRate": bt["metrics"]["win_rate"],
            "equity": bt["equity"],
        })
    return results


def calc_multi_stock(ts_codes: list, start_date: str, end_date: str,
                     period: int = 20, atr_period: int = 14,
                     stop_atr: float = 2.0, risk_ratio: float = 0.01,
                     adj_type: str = "qfq", risk_free: float = 0.02) -> list:
    """多只股票在相同海龟参数下回测对比。"""
    results = []
    for code in ts_codes:
        try:
            resolved = resolve_tscode(code)
            df = fetch_daily(resolved, start_date, end_date)
            df.attrs["adj_type"] = adj_type
            df = apply_adjustment(df, adj_type)
            close = df["close"].astype(float)
            high = df["high"].astype(float)
            low = df["low"].astype(float)
            bt = backtest_turtle(close, high, low, period, atr_period, stop_atr,
                                 risk_ratio, 1_000_000, risk_free)
            results.append({
                "tsCode": df.iloc[0]["ts_code"],
                "name": df.iloc[0]["ts_code"].split('.')[0],
                "cumReturn": bt["metrics"]["cum_return"],
                "mdd": bt["metrics"]["mdd"],
                "annReturn": bt["metrics"]["ann_return"],
                "annVol": bt["metrics"]["ann_vol"],
                "sharpe": bt["metrics"]["sharpe"],
                "nTrade": bt["metrics"]["n_trade"],
                "winRate": bt["metrics"]["win_rate"],
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
    """直接渲染 Task 4 看板页面。"""
    try:
        with open(os.path.join(os.path.dirname(__file__), "dashboard.html"),
                  "r", encoding="utf-8") as f:
            html = f.read()
        return html
    except Exception as e:
        return f"<h1>Task 4 海龟策略看板</h1><p>加载页面失败: {e}</p><p>请确认 dashboard.html 存在。</p>"


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
    海龟策略回测。
    参数:
      tscode: 股票代码或中文名
      start_date / end_date: YYYY-MM-DD（可选）
      adj: 复权方式 none | qfq | hfq（默认 qfq）
      period: 唐奇安通道周期（默认 20）
      atr_period: ATR 计算周期（默认 14）
      stop_atr: 止损 ATR 倍数（默认 2.0）
      risk_ratio: 单笔风险比例（默认 0.01）
      risk_free: 无风险利率年化（默认 0.02）
    """
    tscode = request.args.get("tscode", "").strip()
    if not tscode:
        return jsonify({"error": "请提供股票代码"})

    try:
        adj_type = request.args.get("adj", "qfq").strip().lower()
        if adj_type not in ("none", "qfq", "hfq"):
            adj_type = "qfq"

        period = int(request.args.get("period", 20))
        atr_period = int(request.args.get("atr_period", 14))
        stop_atr = float(request.args.get("stop_atr", 2.0))
        risk_ratio = float(request.args.get("risk_ratio", 0.01))
        risk_free = float(request.args.get("risk_free", 0.02))

        if period < 2 or period > 250:
            return jsonify({"error": "通道周期应在 2~250 之间"})
        if atr_period < 1 or atr_period > 100:
            return jsonify({"error": "ATR 周期应在 1~100 之间"})
        if stop_atr <= 0 or stop_atr > 10:
            return jsonify({"error": "止损 ATR 倍数应在 (0, 10] 之间"})

        resolved = resolve_tscode(tscode)
        df = fetch_daily(
            resolved,
            start_date=request.args.get("start_date") or None,
            end_date=request.args.get("end_date") or None,
        )
        df.attrs["adj_type"] = adj_type
        df = apply_adjustment(df, adj_type)
        result = calc_backtest(df, period, atr_period, stop_atr, risk_ratio, risk_free)
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)})


@app.route("/api/compare_params")
def api_compare_params():
    """
    多组通道周期回测对比。
    """
    tscode = request.args.get("tscode", "").strip()
    if not tscode:
        return jsonify({"error": "请提供股票代码"})

    try:
        adj_type = request.args.get("adj", "qfq").strip().lower()
        if adj_type not in ("none", "qfq", "hfq"):
            adj_type = "qfq"

        params_raw = request.args.get("periods", "10,20,30,50")
        periods = []
        for part in params_raw.split(","):
            part = part.strip()
            if not part:
                continue
            p = int(part)
            if 2 <= p <= 250:
                periods.append(p)
        if not periods:
            periods = [10, 20, 30, 50]

        atr_period = int(request.args.get("atr_period", 14))
        stop_atr = float(request.args.get("stop_atr", 2.0))
        risk_ratio = float(request.args.get("risk_ratio", 0.01))
        risk_free = float(request.args.get("risk_free", 0.02))

        resolved = resolve_tscode(tscode)
        df = fetch_daily(
            resolved,
            start_date=request.args.get("start_date") or None,
            end_date=request.args.get("end_date") or None,
        )
        df.attrs["adj_type"] = adj_type
        df = apply_adjustment(df, adj_type)

        results = calc_multi_param(df, periods, atr_period, stop_atr, risk_ratio, risk_free)
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
    多只股票在相同海龟参数下回测对比。
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

        period = int(request.args.get("period", 20))
        atr_period = int(request.args.get("atr_period", 14))
        stop_atr = float(request.args.get("stop_atr", 2.0))
        risk_ratio = float(request.args.get("risk_ratio", 0.01))
        risk_free = float(request.args.get("risk_free", 0.02))

        results = calc_multi_stock(
            codes,
            request.args.get("start_date") or None,
            request.args.get("end_date") or None,
            period, atr_period, stop_atr, risk_ratio, adj_type, risk_free,
        )
        return jsonify({
            "param": f"通道{period}日",
            "period": period,
            "results": results,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)})


# ===== 启动 =====
if __name__ == "__main__":
    print("🐢 正在预加载股票基础信息...")
    try:
        count = len(load_stock_list())
        print(f"   ✅ 已加载 {count} 只股票")
    except Exception as e:
        print(f"   ⚠️ 加载股票列表失败（不影响查询，仅搜索建议不可用）: {e}")
    print("🐢 启动 Task 4 海龟交易策略看板服务器...")
    print("   浏览器打开: http://localhost:5004")
    print("   支持：唐奇安通道、ATR 仓位、止损倍数、多参数/多股票对比")
    app.run(host="0.0.0.0", port=5004, debug=False)
