#!/usr/bin/env python3
"""
Task 6 机器学习回归策略看板后端
================================
提供指数成分股拉取、批量日线数据、股票搜索 API。
所有 ML 计算在前端 regression_engine.js 中完成。

用法：
  python task6_backend.py
  浏览器打开 http://localhost:5006
"""

import os, json, time
from flask import Flask, request, jsonify, send_from_directory
import tushare as ts

# ===== 配置 =====
TOKEN = os.environ.get(
    "TUSHARE_TOKEN",
    "6f9eca8f7a38eda0bdd0ebbd1c9063498b26a7ee96c374eaba4167eb",
)
ts.set_token(TOKEN)
pro = ts.pro_api()

app = Flask(__name__)

# ===== 预设指数列表 =====
INDEX_LIST = [
    {"code": "000300.SH", "name": "沪深300",   "type": "宽基", "count": 300},
    {"code": "000016.SH", "name": "上证50",    "type": "宽基", "count": 50},
    {"code": "399006.SZ", "name": "创业板指",   "type": "宽基", "count": 100},
    {"code": "000905.SH", "name": "中证500",   "type": "宽基", "count": 500},
    {"code": "000932.SH", "name": "中证消费",   "type": "行业", "count": 100},
    {"code": "000933.SH", "name": "中证医药",   "type": "行业", "count": 100},
    {"code": "000935.SH", "name": "中证信息",   "type": "行业", "count": 100},
    {"code": "399986.SZ", "name": "中证银行",   "type": "行业", "count": 50},
]

# ===== 预设成分股（当 Tushare index_member 权限不足时使用） =====
PRESET_CONSTITUENTS = {
    "000300.SH": [
        "000001.SZ","000002.SZ","000063.SZ","000333.SZ","000338.SZ",
        "000568.SZ","000651.SZ","000725.SZ","000776.SZ","000858.SZ",
        "002027.SZ","002074.SZ","002230.SZ","002271.SZ","002304.SZ",
        "002352.SZ","002415.SZ","002475.SZ","002594.SZ","002714.SZ",
        "300015.SZ","300059.SZ","300124.SZ","300274.SZ","300308.SZ",
        "300316.SZ","300433.SZ","300498.SZ","300750.SZ","300760.SZ",
        "600000.SH","600009.SH","600016.SH","600019.SH","600025.SH",
        "600028.SH","600029.SH","600030.SH","600031.SH","600036.SH",
        "600048.SH","600050.SH","600085.SH","600104.SH","600196.SH",
        "600276.SH","600309.SH","600346.SH","600406.SH","600436.SH",
        "600438.SH","600519.SH","600547.SH","600570.SH","600585.SH",
        "600588.SH","600600.SH","600690.SH","600745.SH","600809.SH",
        "600837.SH","600886.SH","600887.SH","600900.SH","600918.SH",
        "600919.SH","600926.SH","600941.SH","601012.SH","601066.SH",
        "601088.SH","601138.SH","601166.SH","601169.SH","601225.SH",
        "601288.SH","601318.SH","601328.SH","601333.SH","601390.SH",
        "601628.SH","601633.SH","601668.SH","601669.SH","601688.SH",
        "601728.SH","601766.SH","601800.SH","601818.SH","601857.SH",
        "601881.SH","601888.SH","601899.SH","601919.SH","601985.SH",
        "603259.SH","603288.SH","603501.SH","603799.SH","688005.SH",
        "688008.SH","688009.SH","688012.SH","688036.SH","688111.SH",
        "688185.SH","688256.SH","688396.SH","688599.SH",
    ],
    "000016.SH": [
        "600000.SH","600009.SH","600016.SH","600019.SH","600025.SH",
        "600028.SH","600029.SH","600030.SH","600031.SH","600036.SH",
        "600048.SH","600050.SH","600085.SH","600104.SH","600196.SH",
        "600276.SH","600309.SH","600346.SH","600406.SH","600436.SH",
        "600438.SH","600519.SH","600547.SH","600570.SH","600585.SH",
        "600588.SH","600600.SH","600690.SH","600745.SH","600809.SH",
        "600837.SH","600886.SH","600887.SH","600900.SH","600918.SH",
        "600919.SH","600926.SH","600941.SH","601012.SH","601066.SH",
        "601088.SH","601138.SH","601166.SH","601169.SH","601225.SH",
        "601288.SH","601318.SH","601328.SH","601333.SH","601390.SH",
    ],
}

# 行业筛选条件（用于行业指数）
INDUSTRY_FILTERS = {
    "000932.SH": ["食品饮料","家用电器","商业贸易","纺织服装","休闲服务","轻工制造","农林牧渔"],
    "000933.SH": ["医药生物"],
    "000935.SH": ["计算机","通信","电子","传媒"],
    "399986.SZ": ["银行"],
}

# ===== 缓存目录 =====
_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".task6_cache")
os.makedirs(_CACHE_DIR, exist_ok=True)

# ===== CORS =====
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    # 禁止缓存 HTML/JS（开发阶段）
    if response.content_type and "html" in response.content_type:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

@app.route("/<path:p>", methods=["OPTIONS"])
def cors_preflight(p):
    return app.make_default_options_response()

# ===== 股票基础信息缓存 =====
_stock_basic_cache = None

def get_stock_basic():
    global _stock_basic_cache
    if _stock_basic_cache is not None:
        return _stock_basic_cache
    cache_file = os.path.join(_CACHE_DIR, "stock_basic.json")
    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            _stock_basic_cache = json.load(f)
            return _stock_basic_cache
    try:
        df = pro.stock_basic(exchange="", list_status="L",
                             fields="ts_code,symbol,name,industry,market")
        stocks = df.to_dict("records")
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(stocks, f, ensure_ascii=False)
        _stock_basic_cache = stocks
        return stocks
    except Exception as e:
        print(f"[ERROR] 获取股票基础信息失败: {e}")
        return []

# ===== 单只股票日线缓存 =====
def get_daily_cached(code, start="20220101", end="20241231"):
    cache_file = os.path.join(_CACHE_DIR, f"daily_{code}.json")
    # 检查缓存是否覆盖请求范围
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
            cached_start = cached.get("_meta", {}).get("start", "")
            cached_end = cached.get("_meta", {}).get("end", "")
            if cached_start <= start and cached_end >= end:
                return cached.get("data", [])
        except Exception:
            pass
    # 实时拉取
    try:
        df = pro.daily(ts_code=code, start_date=start, end_date=end)
        if df is None or len(df) == 0:
            return []
        df = df.sort_values("trade_date")
        records = []
        for _, row in df.iterrows():
            d = str(row["trade_date"])  # YYYYMMDD
            date_fmt = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
            records.append({
                "ts_code": code,
                "trade_date": date_fmt,
                "open":   round(float(row["open"]), 2),
                "high":   round(float(row["high"]), 2),
                "low":    round(float(row["low"]), 2),
                "close":  round(float(row["close"]), 2),
                "vol":    round(float(row["vol"]), 0),
                "amount": round(float(row["amount"]), 0),
            })
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({"_meta": {"start": start, "end": end}, "data": records}, f)
        return records
    except Exception as e:
        print(f"[ERROR] 获取 {code} 日线失败: {e}")
        return []

# ===== API 路由 =====

@app.route("/api/index_list")
def api_index_list():
    return jsonify(INDEX_LIST)

@app.route("/api/constituents")
def api_constituents():
    index_code = request.args.get("index", "").strip()
    if not index_code:
        return jsonify({"error": "缺少 index 参数"}), 400

    # 尝试 index_member 接口
    try:
        df = pro.index_member(index_code=index_code)
        if df is not None and len(df) > 0:
            members = [{"ts_code": row.get("ts_code", ""), "name": row.get("name", "")}
                       for _, row in df.iterrows()]
            return jsonify({"index_code": index_code, "count": len(members), "members": members})
    except Exception as e:
        print(f"[WARN] index_member 失败: {e}")

    # 尝试 index_weight 接口
    try:
        df = pro.index_weight(index_code=index_code, start_date="20240601", end_date="20241231")
        if df is not None and len(df) > 0:
            df = df.drop_duplicates(subset=["con_code"], keep="first")
            members = [{"ts_code": row.get("con_code", ""), "name": row.get("con_name", "")}
                       for _, row in df.iterrows()]
            return jsonify({"index_code": index_code, "count": len(members), "members": members})
    except Exception as e:
        print(f"[WARN] index_weight 失败: {e}")

    # Fallback 1: 预设成分股列表
    if index_code in PRESET_CONSTITUENTS:
        codes = PRESET_CONSTITUENTS[index_code]
        stocks = get_stock_basic()
        name_map = {s["ts_code"]: s.get("name", "") for s in stocks}
        members = [{"ts_code": c, "name": name_map.get(c, c)} for c in codes]
        return jsonify({"index_code": index_code, "count": len(members), "members": members})

    # Fallback 2: 行业筛选
    if index_code in INDUSTRY_FILTERS:
        industries = INDUSTRY_FILTERS[index_code]
        stocks = get_stock_basic()
        members = [{"ts_code": s["ts_code"], "name": s.get("name", "")}
                   for s in stocks if s.get("industry", "") in industries]
        # 限制最多 80 只（避免拉取太慢）
        members = members[:80]
        return jsonify({"index_code": index_code, "count": len(members), "members": members})

    # Fallback 3: 创业板指 — 筛选 300xxx
    if index_code == "399006.SZ":
        stocks = get_stock_basic()
        members = [{"ts_code": s["ts_code"], "name": s.get("name", "")}
                   for s in stocks if s["ts_code"].startswith("300")]
        members = members[:80]
        return jsonify({"index_code": index_code, "count": len(members), "members": members})

    return jsonify({"error": f"无法获取 {index_code} 成分股，请选择其他指数或使用搜索功能添加个股"}), 403

@app.route("/api/daily")
def api_daily():
    """批量获取日线数据。支持 codes 逗号分隔，或直接传 index 指数代码。"""
    codes_str = request.args.get("codes", "").strip()
    index_code = request.args.get("index", "").strip()
    start = request.args.get("start", "20220101")
    end = request.args.get("end", "20241231")
    # 如果传了 index，先获取成分股
    if index_code and not codes_str:
        try:
            resp = api_constituents()
            data = resp.get_json()
            if "error" in data:
                return jsonify(data), 403
            codes_str = ",".join([m["ts_code"] for m in data["members"]])
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    if not codes_str:
        return jsonify({"error": "缺少 codes 或 index 参数"}), 400
    codes = [c.strip() for c in codes_str.split(",") if c.strip()]
    result = {}
    total = len(codes)
    for i, code in enumerate(codes):
        data = get_daily_cached(code, start, end)
        if data:
            result[code] = data
        # Tushare 频率限制：每 10 只暂停一下
        if (i + 1) % 10 == 0 and i + 1 < total:
            time.sleep(0.3)
    return jsonify({
        "data": result,
        "count": len(result),
        "total": total,
        "start": start,
        "end": end,
    })

@app.route("/api/stock_search")
def api_stock_search():
    q = request.args.get("q", "").strip()
    if not q or len(q) < 1:
        return jsonify([])
    stocks = get_stock_basic()
    q_lower = q.lower()
    results = []
    for s in stocks:
        name = s.get("name", "")
        ts_code = s.get("ts_code", "")
        symbol = s.get("symbol", "")
        if q_lower in name.lower() or q_lower in ts_code.lower() or q_lower in symbol.lower():
            results.append({
                "ts_code": ts_code,
                "name": name,
                "industry": s.get("industry", ""),
            })
            if len(results) >= 30:
                break
    return jsonify(results)

@app.route("/api/stock_detail")
def api_stock_detail():
    """获取单只股票的日线数据（带名称）"""
    code = request.args.get("code", "").strip()
    start = request.args.get("start", "20220101")
    end = request.args.get("end", "20241231")
    if not code:
        return jsonify({"error": "缺少 code 参数"}), 400
    # 获取名称
    name = code
    stocks = get_stock_basic()
    for s in stocks:
        if s.get("ts_code") == code:
            name = s.get("name", code)
            break
    data = get_daily_cached(code, start, end)
    return jsonify({"ts_code": code, "name": name, "data": data, "count": len(data)})

# ===== 静态文件 =====
_STATIC_FILES = {"dashboard.html", "regression_engine.js"}

@app.route("/")
def index_page():
    return send_from_directory(".", "dashboard.html")

@app.route("/<path:filename>")
def static_files(filename):
    if filename in _STATIC_FILES:
        return send_from_directory(".", filename)
    return jsonify({"error": "Not found"}), 404

# ===== 入口 =====
if __name__ == "__main__":
    print("=" * 50)
    print("Task 6 机器学习回归策略看板")
    print("=" * 50)
    print(f"预设指数: {len(INDEX_LIST)} 个")
    for idx in INDEX_LIST:
        print(f"  · {idx['name']:6s} ({idx['code']}) — {idx['type']}")
    print("-" * 50)
    print("浏览器打开: http://localhost:5006")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5006, debug=True)
