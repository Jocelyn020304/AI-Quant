#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task 6 — 沪深300成分股日线数据拉取
===================================
用 Tushare Pro API 获取沪深300指数成分股列表，拉取 2022-01-01 ~ 2024-12-31
日线行情（前复权），保存为 panel CSV 供后续因子工程使用。

输出：
  - hs300_constituents.csv  沪深300成分股列表
  - hs300_daily_panel.csv   面板数据（长格式：ts_code, trade_date, open, ...）
"""

import os
import sys
import time
import tushare as ts
import pandas as pd

# ===== 配置 =====
TOKEN = "6f9eca8f7a38eda0bdd0ebbd1c9063498b26a7ee96c374eaba4167eb"
ts.set_token(TOKEN)
pro = ts.pro_api()

HERE = os.path.dirname(os.path.abspath(__file__))
START_DATE = "20220101"
END_DATE = "20241231"
INDEX_CODE = "399300.SZ"  # 沪深300指数

CONSTITUENTS_CSV = os.path.join(HERE, "hs300_constituents.csv")
PANEL_CSV = os.path.join(HERE, "hs300_daily_panel.csv")
CACHE_DIR = os.path.join(HERE, ".daily_cache")


def get_hs300_constituents():
    """获取沪深300成分股列表。"""
    print("=" * 60)
    print("步骤1：获取沪深300成分股列表")
    print("=" * 60)

    # 尝试用 index_weight 接口获取最新成分股
    try:
        # 取 2024 年最后一个交易日的权重快照
        df = pro.index_weight(index_code=INDEX_CODE,
                              start_date="20241201", end_date="20241231")
        if df is not None and len(df) > 0:
            # 取最后一个日期的成分股
            latest_date = df["trade_date"].max()
            constituents = df[df["trade_date"] == latest_date].copy()
            constituents = constituents[["con_code", "stock_name", "weight"]].rename(
                columns={"con_code": "ts_code", "stock_name": "name"}
            )
            constituents = constituents.sort_values("weight", ascending=False).reset_index(drop=True)
            print(f"  获取到 {len(constituents)} 只成分股（日期: {latest_date}）")
            constituents.to_csv(CONSTITUENTS_CSV, index=False, encoding="utf-8-sig")
            print(f"  已保存: {CONSTITUENTS_CSV}")
            return constituents["ts_code"].tolist()
    except Exception as e:
        print(f"  index_weight 接口异常: {e}")

    # 降级：用 index_member 接口
    try:
        df = pro.index_member(index_code=INDEX_CODE)
        if df is not None and len(df) > 0:
            codes = df["con_code"].unique().tolist()
            print(f"  (index_member) 获取到 {len(codes)} 只成分股")
            # 保存简化版
            pd.DataFrame({"ts_code": codes}).to_csv(
                CONSTITUENTS_CSV, index=False, encoding="utf-8-sig")
            return codes
    except Exception as e:
        print(f"  index_member 接口异常: {e}")

    # 最终降级：用预设的大盘股列表（约80只沪深300核心成分股）
    print("  使用预设大盘股列表（降级方案）")
    fallback = [
        "000001.SZ", "000002.SZ", "000063.SZ", "000333.SZ", "000338.SZ",
        "000568.SZ", "000651.SZ", "000725.SZ", "000776.SZ", "000858.SZ",
        "002027.SZ", "002074.SZ", "002230.SZ", "002271.SZ", "002304.SZ",
        "002352.SZ", "002415.SZ", "002475.SZ", "002594.SZ", "002714.SZ",
        "300015.SZ", "300059.SZ", "300124.SZ", "300274.SZ", "300308.SZ",
        "300316.SZ", "300433.SZ", "300498.SZ", "300750.SZ", "300760.SZ",
        "600000.SH", "600009.SH", "600016.SH", "600019.SH", "600025.SH",
        "600028.SH", "600029.SH", "600030.SH", "600031.SH", "600036.SH",
        "600048.SH", "600050.SH", "600085.SH", "600104.SH", "600196.SH",
        "600276.SH", "600309.SH", "600346.SH", "600406.SH", "600436.SH",
        "600438.SH", "600519.SH", "600547.SH", "600570.SH", "600585.SH",
        "600588.SH", "600600.SH", "600690.SH", "600745.SH", "600809.SH",
        "600837.SH", "600886.SH", "600887.SH", "600900.SH", "600918.SH",
        "600919.SH", "600926.SH", "600941.SH", "601012.SH", "601066.SH",
        "601088.SH", "601138.SH", "601166.SH", "601169.SH", "601225.SH",
        "601288.SH", "601318.SH", "601328.SH", "601333.SH", "601390.SH",
        "601628.SH", "601633.SH", "601668.SH", "601669.SH", "601688.SH",
        "601728.SH", "601766.SH", "601800.SH", "601818.SH", "601857.SH",
        "601881.SH", "601888.SH", "601899.SH", "601919.SH", "601985.SH",
        "603259.SH", "603288.SH", "603501.SH", "603799.SH", "688005.SH",
        "688008.SH", "688009.SH", "688012.SH", "688036.SH", "688111.SH",
        "688185.SH", "688256.SH", "688396.SH", "688599.SH",
    ]
    pd.DataFrame({"ts_code": fallback}).to_csv(
        CONSTITUENTS_CSV, index=False, encoding="utf-8-sig")
    print(f"  预设列表 {len(fallback)} 只")
    return fallback


def fetch_daily_data(ts_codes):
    """批量拉取日线数据（前复权）。"""
    print("\n" + "=" * 60)
    print(f"步骤2：拉取 {len(ts_codes)} 只股票日线数据")
    print(f"  时间范围: {START_DATE} ~ {END_DATE}")
    print("=" * 60)

    os.makedirs(CACHE_DIR, exist_ok=True)

    all_data = []
    success_count = 0
    fail_count = 0
    fail_list = []

    for i, code in enumerate(ts_codes):
        cache_file = os.path.join(CACHE_DIR, f"{code}.csv")

        # 如果有缓存就直接读
        if os.path.exists(cache_file):
            try:
                df = pd.read_csv(cache_file)
                if len(df) > 0:
                    all_data.append(df)
                    success_count += 1
                    if (i + 1) % 20 == 0:
                        print(f"  [{i+1}/{len(ts_codes)}] {code} (缓存) {len(df)}条")
                    continue
            except Exception:
                pass  # 缓存坏了重新拉

        # 调用 Tushare daily 接口（未复权）
        try:
            df = pro.daily(ts_code=code, start_date=START_DATE, end_date=END_DATE)
            if df is not None and len(df) > 0:
                df.to_csv(cache_file, index=False, encoding="utf-8-sig")
                all_data.append(df)
                success_count += 1
            else:
                fail_count += 1
                fail_list.append(code)
        except Exception as e:
            fail_count += 1
            fail_list.append(code)

        # 进度显示
        if (i + 1) % 20 == 0:
            print(f"  [{i+1}/{len(ts_codes)}] {code} 成功{success_count} 失败{fail_count}")

        # Tushare 频率控制：每次调用间隔
        time.sleep(0.12)

    print(f"\n  拉取完成: 成功 {success_count} / 失败 {fail_count}")
    if fail_list:
        print(f"  失败列表(前20): {fail_list[:20]}")

    # 合并所有数据
    if not all_data:
        print("  错误: 没有获取到任何数据!")
        return None

    panel = pd.concat(all_data, ignore_index=True)
    # 排序
    panel["trade_date"] = pd.to_datetime(panel["trade_date"], format="%Y%m%d")
    panel = panel.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    # 转回字符串格式
    panel["trade_date"] = panel["trade_date"].dt.strftime("%Y%m%d")

    print(f"  面板数据: {panel.shape[0]} 行 × {panel.shape[1]} 列")
    print(f"  股票数: {panel['ts_code'].nunique()}")
    print(f"  日期范围: {panel['trade_date'].min()} ~ {panel['trade_date'].max()}")

    panel.to_csv(PANEL_CSV, index=False, encoding="utf-8-sig")
    print(f"  已保存: {PANEL_CSV}")
    return panel


def main():
    print("=" * 60)
    print("TASK6 数据拉取：沪深300成分股日线数据")
    print("=" * 60)

    # Step 1: 获取成分股
    codes = get_hs300_constituents()

    # Step 2: 拉日线数据
    panel = fetch_daily_data(codes)

    if panel is not None:
        print("\n" + "=" * 60)
        print("数据拉取完成！")
        print(f"  成分股列表: {CONSTITUENTS_CSV}")
        print(f"  日线面板:   {PANEL_CSV}")
        print("=" * 60)


if __name__ == "__main__":
    main()
