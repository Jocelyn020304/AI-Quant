#!/usr/bin/env python3
"""
Task 6 静态数据生成器
====================
从 .task6_cache/ 缓存中读取已拉取的日线数据，
合并成压缩格式的静态 JSON 文件，供 GitHub Pages 纯静态看板使用。

输出：
  Task 6/static_data.json   — 所有指数成分股日线 + 搜索库

用法：
  cd "Task 6"
  python gen_static_data.py
"""

import json, os, sys, time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, ".task6_cache")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "static_data.json")

# ===== 指数成分股定义（与 dashboard.html INDEX_LIST + backend PRESET_CONSTITUENTS 对齐）=====
INDEX_DEFINITIONS = {
    "000016.SH": {
        "name": "上证50",
        "type": "宽基",
        "codes": [
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
    },
    "000300.SH": {
        "name": "沪深300",
        "type": "宽基",
        "codes": [
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
    },
}


def load_stock_basic():
    """加载股票基础信息"""
    path = os.path.join(CACHE_DIR, "stock_basic.json")
    if not os.path.exists(path):
        print(f"[ERROR] 找不到 {path}，请先运行 task6_backend.py 拉取一次数据")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_daily(code):
    """从缓存加载单只股票日线"""
    path = os.path.join(CACHE_DIR, f"daily_{code}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        cached = json.load(f)
    return cached.get("data", [])


def compress_daily(records):
    """
    将 [{ts_code, trade_date, open, high, low, close, vol, amount}, ...]
    压缩为按列存储的紧凑格式:
      {d: [dates], o: [opens], h: [highs], l: [lows], c: [closes], v: [vols], a: [amounts]}
    """
    if not records:
        return None
    # 按 trade_date 排序
    records.sort(key=lambda r: r.get("trade_date", ""))
    return {
        "d": [r["trade_date"] for r in records],
        "o": [r["open"] for r in records],
        "h": [r["high"] for r in records],
        "l": [r["low"] for r in records],
        "c": [r["close"] for r in records],
        "v": [r["vol"] for r in records],
        "a": [r["amount"] for r in records],
    }


def main():
    print("=" * 55)
    print("Task 6 静态数据生成器")
    print("=" * 55)

    t0 = time.time()

    # 1. 加载股票名称映射
    print("\n[1/3] 加载股票基础信息...")
    stock_basic = load_stock_basic()
    name_map = {s["ts_code"]: s.get("name", "") for s in stock_basic}
    industry_map = {s["ts_code"]: s.get("industry", "") for s in stock_basic}
    print(f"       共 {len(stock_basic)} 只股票")

    # 2. 为每个指数生成数据
    output = {
        "_meta": {"generated": time.strftime("%Y-%m-%d %H:%M:%S"), "version": 1},
        "indices": {},
        "stocks": {},       # code -> compressed daily data
        "search_db": [],    # 搜索用：[{c, n, i}, ...]
    }

    print("\n[2/3] 合并指数成分股日线数据...")
    total_stocks = 0
    total_bars = 0

    for idx_code, idx_def in INDEX_DEFINITIONS.items():
        codes = idx_def["codes"]
        members = []
        idx_stocks = {}

        for code in codes:
            name = name_map.get(code, code)
            daily = load_daily(code)

            if daily:
                compressed = compress_daily(daily)
                if compressed:
                    idx_stocks[code] = compressed
                    output["stocks"][code] = compressed  # 全局也存一份，供搜索个股复用
                    total_bars += len(daily)
                    total_stocks += 1
                members.append({"ts_code": code, "name": name})
            else:
                # 缓存中没有这只股票的数据
                members.append({"ts_code": code, "name": name})
                print(f"       ⚠️  {code} ({name}) 无缓存数据，跳过")

        output["indices"][idx_code] = {
            "name": idx_def["name"],
            "type": idx_def["type"],
            "members": members,
            "available_codes": list(idx_stocks.keys()),
        }
        print(f"       {idx_def['name']} ({idx_code}): {len(idx_stocks)}/{len(codes)} 只有数据")

    # 3. 生成搜索数据库（只用已有数据的股票）
    print("\n[3/3] 生成搜索数据库...")
    for code in output["stocks"]:
        output["search_db"].append({
            "c": code,
            "n": name_map.get(code, code),
            "i": industry_map.get(code, ""),
        })
    # 按代码排序
    output["search_db"].sort(key=lambda x: x["c"])

    # 4. 写入文件
    print(f"\n写入 {OUTPUT_FILE} ...")
    json_str = json.dumps(output, ensure_ascii=False, separators=(",", ":"))
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(json_str)

    size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
    elapsed = time.time() - t0

    print(f"\n{'=' * 55}")
    print(f"✅ 生成完成！")
    print(f"   文件大小: {size_mb:.2f} MB")
    print(f"   股票数量: {total_stocks} 只")
    print(f"   K线总数:  {total_bars} 条")
    print(f"   搜索词条: {len(output['search_db'])} 条")
    print(f"   耗时:     {elapsed:.1f}s")
    print(f"{'=' * 55}")

    # 也输出一个 gzip 大小估算
    import zlib
    compressed = zlib.compress(json_str.encode("utf-8"))
    print(f"   Gzip 后约: {len(compressed) / (1024*1024):.2f} MB （浏览器传输实际大小）")


if __name__ == "__main__":
    main()
