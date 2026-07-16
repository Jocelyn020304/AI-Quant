#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TASK6 — 智能决策者：用机器学习定制专属策略
==========================================

基于沪深300成分股日线数据，使用回归型机器学习模型预测股票未来
季度收益率，据此构建 Top-30 横截面选股策略，并在测试集上按季度
再平衡回测，最终对比 Ridge / 决策树 / 随机森林 / GBDT 四类模型
的策略表现。

流程：
  1. 加载面板数据（hs300_daily_panel.csv）
  2. 因子工程：动量 / 波动率 / 换手率 / 量价 / 技术 因子（自变量 X）
  3. 应变量：未来 60 个交易日累计收益率（y）
  4. 时间切分：2022-01 ~ 2023-12 训练，2024-01 ~ 2024-12 测试
  5. 训练四类回归模型
  6. 季度再平衡策略：每季度预测 → 选 Top-30 等权持有
  7. 回测指标 + 多模型对比
  8. 输出 5 张图 + 指标 CSV + 数据字典 JSON

运行环境：隔离 venv（sklearn / pandas / matplotlib）
作者：张靖悦
"""

import os
import json
import warnings
import numpy as np
import pandas as pd
import matplotlib
import matplotlib.font_manager as fm

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# 中文字体
for _fp in (r"C:/Windows/Fonts/simhei.ttf", r"C:/Windows/Fonts/msyh.ttc"):
    if os.path.exists(_fp):
        try:
            fm.fontManager.addfont(_fp)
        except Exception:
            pass
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "SimSun", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.tree import DecisionTreeRegressor
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import mean_squared_error, r2_score

warnings.filterwarnings("ignore")

# ====================== 全局配置 ======================
HERE = os.path.dirname(os.path.abspath(__file__))
PANEL_CSV = os.path.join(HERE, "hs300_daily_panel.csv")

# 输出文件
OUT_NETVALUE = os.path.join(HERE, "TASK6_净值曲线对比.png")
OUT_QUARTERLY = os.path.join(HERE, "TASK6_季度收益柱状图.png")
OUT_DRAWDOWN = os.path.join(HERE, "TASK6_最大回撤对比.png")
OUT_FEATURE = os.path.join(HERE, "TASK6_特征重要性.png")
OUT_SCATTER = os.path.join(HERE, "TASK6_预测vs实际散点图.png")
OUT_METRICS_CSV = os.path.join(HERE, "TASK6_模型回测指标.csv")
OUT_MODEL_COMPARISON_CSV = os.path.join(HERE, "TASK6_模型预测精度对比.csv")
OUT_META_JSON = os.path.join(HERE, "TASK6_模型数据字典.json")

RANDOM_STATE = 42
FUTURE_DAYS = 60  # 未来60个交易日 ≈ 1个季度
TOP_K = 30        # 每季度选 Top-30
TRAIN_END = "20231231"  # 训练集截止
RF_RATE = 0.02   # 无风险利率（年化）

# 因子列表
FEATURES = [
    # 动量类
    "ret_5d", "ret_20d", "ret_60d",
    # 波动率类
    "vol_20d", "vol_60d",
    # 量价类
    "turnover_5d", "turnover_20d", "amount_log", "range_20d",
    # 技术类
    "ma_gap_5_20", "ma_gap_20_60", "rsi_14", "volume_ratio",
]

# 模型显示名 & 颜色
MODEL_LABELS = {
    "ridge": "Ridge 回归",
    "decision_tree": "决策树回归",
    "random_forest": "随机森林回归",
    "gbdt": "梯度提升回归 (GBDT)",
}
MODEL_COLORS = {
    "ridge": "#1f77b4",
    "decision_tree": "#ff7f0e",
    "random_forest": "#2ca02c",
    "gbdt": "#d62728",
}
BENCH_COLOR = "#888888"
BENCH_LABEL = "沪深300等权基准"


# ====================== 1. 加载数据 ======================
def load_panel():
    """加载面板数据。"""
    print("=" * 60)
    print("步骤1：加载面板数据")
    print("=" * 60)
    df = pd.read_csv(PANEL_CSV, encoding="utf-8-sig")
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
    df = df.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    print(f"  原始数据: {df.shape[0]} 行, {df['ts_code'].nunique()} 只股票")
    print(f"  日期范围: {df['trade_date'].min().date()} ~ {df['trade_date'].max().date()}")
    return df


# ====================== 2. 因子工程 ======================
def build_factors(df):
    """计算所有自变量因子和应变量。"""
    print("\n" + "=" * 60)
    print("步骤2：因子工程（自变量 + 应变量）")
    print("=" * 60)

    result_frames = []
    codes = df["ts_code"].unique()
    print(f"  对 {len(codes)} 只股票逐一计算因子...")

    for code in codes:
        sub = df[df["ts_code"] == code].copy()
        if len(sub) < 120:  # 数据太少跳过
            continue
        sub = sub.sort_values("trade_date").reset_index(drop=True)
        close = sub["close"].astype(float)
        vol = sub["vol"].astype(float)
        amount = sub["amount"].astype(float)
        high = sub["high"].astype(float)
        low = sub["low"].astype(float)

        # ---- 动量因子 ----
        sub["ret_5d"] = close.pct_change(5)
        sub["ret_20d"] = close.pct_change(20)
        sub["ret_60d"] = close.pct_change(60)

        # ---- 波动率因子 ----
        daily_ret = close.pct_change()
        sub["vol_20d"] = daily_ret.rolling(20).std()
        sub["vol_60d"] = daily_ret.rolling(60).std()

        # ---- 换手率/成交量因子 ----
        sub["turnover_5d"] = vol.rolling(5).mean() / (vol.rolling(60).mean() + 1e-8)
        sub["turnover_20d"] = vol.rolling(20).mean() / (vol.rolling(60).mean() + 1e-8)
        sub["amount_log"] = np.log1p(amount)

        # ---- 振幅因子 ----
        sub["range_20d"] = ((high.rolling(20).max() - low.rolling(20).min()) / close).replace([np.inf, -np.inf], np.nan)

        # ---- 技术因子 ----
        ma5 = close.rolling(5).mean()
        ma20 = close.rolling(20).mean()
        ma60 = close.rolling(60).mean()
        sub["ma_gap_5_20"] = (ma5 - ma20) / (ma20 + 1e-8)
        sub["ma_gap_20_60"] = (ma20 - ma60) / (ma60 + 1e-8)

        # RSI 14
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-8)
        sub["rsi_14"] = 100 - 100 / (1 + rs)

        # 量比
        sub["volume_ratio"] = vol / (vol.rolling(20).mean() + 1e-8)

        # ---- 应变量：未来 60 日累计收益率 ----
        sub["future_ret_60d"] = close.shift(-FUTURE_DAYS) / close - 1

        result_frames.append(sub)

    panel = pd.concat(result_frames, ignore_index=True)
    # 只去掉因子为 NaN 的行（future_ret_60d 在测试集末端会缺失，属于正常现象）
    panel = panel.dropna(subset=FEATURES)
    # 去掉极端异常值（有 future_ret_60d 的行才过滤）
    mask_valid = panel["future_ret_60d"].notna()
    mask_normal = (panel["future_ret_60d"] > -0.8) & (panel["future_ret_60d"] < 2.0)
    panel.loc[mask_valid & ~mask_normal, "future_ret_60d"] = np.nan

    print(f"  因子计算完成，有效样本: {panel.shape[0]} 行")
    print(f"  股票数: {panel['ts_code'].nunique()}")
    print(f"  因子数: {len(FEATURES)}")
    print(f"  其中有 future_ret_60d 标签的样本: {panel['future_ret_60d'].notna().sum()} 行")
    return panel


# ====================== 3. 划分训练/测试集 ======================
def split_data(panel):
    """按时间切分训练集和测试集。"""
    print("\n" + "=" * 60)
    print("步骤3：划分训练集 / 测试集")
    print("=" * 60)

    train = panel[panel["trade_date"] <= TRAIN_END].copy()
    test = panel[panel["trade_date"] > TRAIN_END].copy()

    # 训练集：必须有 future_ret_60d 标签
    train = train.dropna(subset=["future_ret_60d"])
    # 测试集：保留所有有因子数据的行（策略执行不依赖标签，末端缺标签是正常的）

    print(f"  训练集: {train.shape[0]} 样本, 日期 {train['trade_date'].min().date()} ~ {train['trade_date'].max().date()}")
    print(f"  测试集: {test.shape[0]} 样本, 日期 {test['trade_date'].min().date()} ~ {test['trade_date'].max().date()}")

    # 标准化（仅训练集 fit）
    scaler = StandardScaler()
    X_train = scaler.fit_transform(train[FEATURES])
    X_test = scaler.transform(test[FEATURES])
    y_train = train["future_ret_60d"].values
    # 测试集标签：有 NaN 的行用 0 占位（仅用于精度评估，不影响策略）
    y_test = test["future_ret_60d"].fillna(0).values

    print(f"  标准化完成（训练集 fit, 测试集 transform）")
    return train, test, X_train, X_test, y_train, y_test, scaler


# ====================== 4. 构建并训练模型 ======================
def build_models():
    """构造四类回归模型。"""
    return {
        "ridge": Ridge(alpha=1.0, random_state=RANDOM_STATE),
        "decision_tree": DecisionTreeRegressor(max_depth=6, min_samples_leaf=50, random_state=RANDOM_STATE),
        "random_forest": RandomForestRegressor(n_estimators=200, max_depth=8, min_samples_leaf=20,
                                                n_jobs=-1, random_state=RANDOM_STATE),
        "gbdt": GradientBoostingRegressor(n_estimators=200, max_depth=4, learning_rate=0.05,
                                           subsample=0.8, random_state=RANDOM_STATE),
    }


def train_and_predict(X_train, y_train, X_test, y_test):
    """训练所有模型并预测。"""
    print("\n" + "=" * 60)
    print("步骤4：训练回归模型并预测")
    print("=" * 60)

    models = build_models()
    predictions = {}
    model_accuracy = []

    for name, model in models.items():
        print(f"\n  训练 {MODEL_LABELS[name]} ...")
        model.fit(X_train, y_train)
        pred_train = model.predict(X_train)
        pred_test = model.predict(X_test)

        # 预测精度指标
        mse_test = mean_squared_error(y_test, pred_test)
        r2_test = r2_score(y_test, pred_test)
        mse_train = mean_squared_error(y_train, pred_train)
        r2_train = r2_score(y_train, pred_train)

        # 方向准确率（预测涨/跌方向是否正确）
        direction_acc = np.mean(np.sign(pred_test) == np.sign(y_test))

        print(f"    训练集 R² = {r2_train:.4f}, MSE = {mse_train:.6f}")
        print(f"    测试集 R² = {r2_test:.4f}, MSE = {mse_test:.6f}")
        print(f"    方向准确率 = {direction_acc:.4f}")

        predictions[name] = pred_test
        model_accuracy.append({
            "模型": MODEL_LABELS[name],
            "训练集R²": round(r2_train, 4),
            "测试集R²": round(r2_test, 4),
            "测试集MSE": round(mse_test, 6),
            "方向准确率": round(direction_acc, 4),
        })

    # 保存预测精度对比
    acc_df = pd.DataFrame(model_accuracy)
    acc_df.to_csv(OUT_MODEL_COMPARISON_CSV, index=False, encoding="utf-8-sig")
    print(f"\n  预测精度对比已保存: {OUT_MODEL_COMPARISON_CSV}")

    return models, predictions


# ====================== 5. 季度再平衡策略 ======================
def get_quarter_end_dates(test_df):
    """获取测试集中每个季度的最后交易日。"""
    test_df = test_df.copy()
    test_df["year"] = test_df["trade_date"].dt.year
    test_df["quarter"] = test_df["trade_date"].dt.quarter
    # 每个季度的最后一个交易日
    quarter_ends = test_df.groupby(["year", "quarter"])["trade_date"].max().sort_values()
    return quarter_ends.tolist()


def quarterly_topk_strategy(test_df, predictions, top_k=TOP_K):
    """
    季度再平衡策略：
    在每个季度末，用模型预测值对候选池排序，选 Top-K 等权持有，
    持有到下个季度末，计算该季度的实际组合收益。

    返回每个模型每季度的收益率序列。
    """
    print("\n" + "=" * 60)
    print(f"步骤5：季度再平衡策略（Top-{top_k} 选股）")
    print("=" * 60)

    test_df = test_df.copy()
    test_df["year"] = test_df["trade_date"].dt.year
    test_df["quarter"] = test_df["trade_date"].dt.quarter

    quarter_ends = get_quarter_end_dates(test_df)
    print(f"  测试期季度末日期: {[d.strftime('%Y-%m-%d') for d in quarter_ends]}")

    # 每个模型的策略净值曲线（从1.0开始）
    strategy_results = {}

    for model_name, pred in predictions.items():
        test_df["pred"] = pred

        quarterly_returns = []
        cumulative_nav = [1.0]
        nav_dates = [quarter_ends[0]]

        for i in range(len(quarter_ends) - 1):
            q_end = quarter_ends[i]
            next_q_end = quarter_ends[i + 1]

            # 在 q_end 这天，用模型预测值排序，选 Top-K
            snapshot = test_df[test_df["trade_date"] == q_end].copy()
            if len(snapshot) < top_k:
                # 如果当天股票不够，取全部
                selected = snapshot
            else:
                selected = snapshot.nlargest(top_k, "pred")

            selected_codes = set(selected["ts_code"].values)

            # 计算这批股票从 q_end 到 next_q_end 的实际收益
            period_data = test_df[
                (test_df["trade_date"] > q_end) &
                (test_df["trade_date"] <= next_q_end) &
                (test_df["ts_code"].isin(selected_codes))
            ].copy()

            if len(period_data) == 0 or len(selected_codes) == 0:
                quarterly_returns.append(0.0)
                cumulative_nav.append(cumulative_nav[-1])
                nav_dates.append(next_q_end)
                continue

            # 每只股票的期间收益
            stock_returns = []
            for code in selected_codes:
                stock_data = period_data[period_data["ts_code"] == code].sort_values("trade_date")
                if len(stock_data) < 2:
                    continue
                # 期初价格（q_end 当天收盘）→ 期末价格
                entry_price = snapshot[snapshot["ts_code"] == code]["close"].values[0]
                exit_price = stock_data["close"].values[-1]
                if entry_price > 0:
                    stock_returns.append(exit_price / entry_price - 1)

            if len(stock_returns) > 0:
                port_ret = np.mean(stock_returns)  # 等权组合
            else:
                port_ret = 0.0

            quarterly_returns.append(port_ret)
            cumulative_nav.append(cumulative_nav[-1] * (1 + port_ret))
            nav_dates.append(next_q_end)

        strategy_results[model_name] = {
            "quarterly_returns": quarterly_returns,
            "nav": np.array(cumulative_nav),
            "nav_dates": nav_dates,
            "quarter_ends": [d.strftime("%Y-%m-%d") for d in quarter_ends[1:]],
        }
        print(f"  {MODEL_LABELS[model_name]}: 季度收益 = {[f'{r*100:.2f}%' for r in quarterly_returns]}, "
              f"累计净值 = {cumulative_nav[-1]:.4f}")

    # ---- 基准：沪深300等权（全样本等权持有，不选股）----
    benchmark_returns = []
    benchmark_nav = [1.0]
    nav_dates_bench = [quarter_ends[0]]

    for i in range(len(quarter_ends) - 1):
        q_end = quarter_ends[i]
        next_q_end = quarter_ends[i + 1]

        snapshot = test_df[test_df["trade_date"] == q_end]
        all_codes = set(snapshot["ts_code"].values)

        period_data = test_df[
            (test_df["trade_date"] > q_end) &
            (test_df["trade_date"] <= next_q_end) &
            (test_df["ts_code"].isin(all_codes))
        ]

        stock_returns = []
        for code in all_codes:
            stock_data = period_data[period_data["ts_code"] == code].sort_values("trade_date")
            if len(stock_data) < 2:
                continue
            entry_price = snapshot[snapshot["ts_code"] == code]["close"].values[0]
            exit_price = stock_data["close"].values[-1]
            if entry_price > 0:
                stock_returns.append(exit_price / entry_price - 1)

        if len(stock_returns) > 0:
            bench_ret = np.mean(stock_returns)
        else:
            bench_ret = 0.0

        benchmark_returns.append(bench_ret)
        benchmark_nav.append(benchmark_nav[-1] * (1 + bench_ret))
        nav_dates_bench.append(next_q_end)

    strategy_results["benchmark"] = {
        "quarterly_returns": benchmark_returns,
        "nav": np.array(benchmark_nav),
        "nav_dates": nav_dates_bench,
        "quarter_ends": [d.strftime("%Y-%m-%d") for d in quarter_ends[1:]],
    }
    print(f"  {BENCH_LABEL}: 季度收益 = {[f'{r*100:.2f}%' for r in benchmark_returns]}, "
          f"累计净值 = {benchmark_nav[-1]:.4f}")

    return strategy_results


# ====================== 6. 回测指标 ======================
def calc_metrics(strategy_results):
    """计算每个模型/基准的核心回测指标。"""
    print("\n" + "=" * 60)
    print("步骤6：计算回测核心指标")
    print("=" * 60)

    metrics = []
    for name, res in strategy_results.items():
        nav = res["nav"]
        q_rets = np.array(res["quarterly_returns"])

        # 累计收益
        total_return = nav[-1] - 1.0
        # 年化收益（假设4个季度=1年）
        n_years = len(q_rets) / 4.0
        if n_years > 0 and nav[-1] > 0:
            annual_return = nav[-1] ** (1 / n_years) - 1
        else:
            annual_return = 0.0
        # 年化波动率（季度收益 × √4）
        annual_vol = np.std(q_rets, ddof=1) * np.sqrt(4) if len(q_rets) > 1 else 0.0
        # 夏普比率
        sharpe = (annual_return - RF_RATE) / annual_vol if annual_vol > 0 else 0.0
        # 最大回撤
        peak = np.maximum.accumulate(nav)
        drawdown = (nav - peak) / peak
        max_dd = np.min(drawdown)
        # 胜率（季度正收益比例）
        win_rate = np.mean(q_rets > 0) if len(q_rets) > 0 else 0.0

        label = MODEL_LABELS.get(name, BENCH_LABEL)
        metrics.append({
            "模型": label,
            "累计收益": f"{total_return*100:.2f}%",
            "年化收益": f"{annual_return*100:.2f}%",
            "年化波动率": f"{annual_vol*100:.2f}%",
            "夏普比率": f"{sharpe:.4f}",
            "最大回撤": f"{max_dd*100:.2f}%",
            "季度胜率": f"{win_rate*100:.1f}%",
        })
        print(f"  {label}: 累计{total_return*100:.2f}% | 年化{annual_return*100:.2f}% | "
              f"夏普{sharpe:.4f} | MDD{max_dd*100:.2f}% | 胜率{win_rate*100:.1f}%")

    metrics_df = pd.DataFrame(metrics)
    metrics_df.to_csv(OUT_METRICS_CSV, index=False, encoding="utf-8-sig")
    print(f"\n  指标表已保存: {OUT_METRICS_CSV}")
    return metrics_df


# ====================== 7. 绘图 ======================
def plot_nav_curves(strategy_results):
    """绘制净值曲线对比图。"""
    fig, ax = plt.subplots(figsize=(12, 6.5), dpi=150)

    for name, res in strategy_results.items():
        dates = [pd.Timestamp(d) for d in res["nav_dates"]]
        label = MODEL_LABELS.get(name, BENCH_LABEL)
        color = MODEL_COLORS.get(name, BENCH_COLOR)
        ls = "-" if name != "benchmark" else "--"
        lw = 2.0 if name != "benchmark" else 1.5
        ax.plot(dates, res["nav"], label=label, color=color, linestyle=ls, linewidth=lw)

    ax.axhline(y=1.0, color="gray", linestyle=":", linewidth=0.8, alpha=0.5)
    ax.set_xlabel("日期", fontsize=12)
    ax.set_ylabel("策略净值", fontsize=12)
    ax.set_title("图1  四类回归模型 Top-30 选股策略净值曲线对比", fontsize=14, fontweight="bold")
    ax.legend(fontsize=9, loc="upper left")
    ax.grid(alpha=0.25)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.tick_params(axis="x", rotation=30)
    plt.tight_layout()
    plt.savefig(OUT_NETVALUE, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  [输出] 净值曲线: {OUT_NETVALUE}")


def plot_quarterly_returns(strategy_results):
    """绘制季度收益率柱状图。"""
    # 排除基准
    model_names = [k for k in strategy_results if k != "benchmark"]
    bench = strategy_results["benchmark"]
    quarter_labels = bench["quarter_ends"]

    n_models = len(model_names)
    n_quarters = len(quarter_labels)
    x = np.arange(n_quarters)
    width = 0.8 / (n_models + 1)  # +1 for benchmark

    fig, ax = plt.subplots(figsize=(12, 6.5), dpi=150)

    for i, name in enumerate(model_names):
        res = strategy_results[name]
        offset = (i - n_models / 2) * width
        ax.bar(x + offset, np.array(res["quarterly_returns"]) * 100, width,
               label=MODEL_LABELS[name], color=MODEL_COLORS[name], alpha=0.85)

    # 基准
    offset = (n_models - n_models / 2) * width
    ax.bar(x + offset, np.array(bench["quarterly_returns"]) * 100, width,
           label=BENCH_LABEL, color=BENCH_COLOR, alpha=0.6, hatch="//")

    ax.axhline(y=0, color="black", linewidth=0.8)
    ax.set_xlabel("季度", fontsize=12)
    ax.set_ylabel("季度收益率 (%)", fontsize=12)
    ax.set_title("图2  各模型季度收益率对比", fontsize=14, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(quarter_labels, fontsize=10)
    ax.legend(fontsize=9, loc="upper right", ncol=2)
    ax.grid(alpha=0.2, axis="y")
    plt.tight_layout()
    plt.savefig(OUT_QUARTERLY, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  [输出] 季度收益柱状图: {OUT_QUARTERLY}")


def plot_drawdown(strategy_results):
    """绘制最大回撤对比图。"""
    fig, ax = plt.subplots(figsize=(12, 5.5), dpi=150)

    for name, res in strategy_results.items():
        dates = [pd.Timestamp(d) for d in res["nav_dates"]]
        nav = res["nav"]
        peak = np.maximum.accumulate(nav)
        drawdown = (nav - peak) / peak * 100  # 转百分比
        label = MODEL_LABELS.get(name, BENCH_LABEL)
        color = MODEL_COLORS.get(name, BENCH_COLOR)
        ls = "-" if name != "benchmark" else "--"
        ax.plot(dates, drawdown, label=label, color=color, linestyle=ls, linewidth=1.5)

    ax.fill_between([pd.Timestamp(d) for d in strategy_results["ridge"]["nav_dates"]],
                    0, -50, alpha=0.02, color="red")
    ax.axhline(y=0, color="black", linewidth=0.5)
    ax.set_xlabel("日期", fontsize=12)
    ax.set_ylabel("回撤幅度 (%)", fontsize=12)
    ax.set_title("图3  各模型最大回撤曲线对比", fontsize=14, fontweight="bold")
    ax.legend(fontsize=9, loc="lower left")
    ax.grid(alpha=0.25)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.tick_params(axis="x", rotation=30)
    plt.tight_layout()
    plt.savefig(OUT_DRAWDOWN, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  [输出] 回撤曲线: {OUT_DRAWDOWN}")


def plot_feature_importance(models):
    """绘制特征重要性图（随机森林 + GBDT）。"""
    tree_models = {"random_forest": models["random_forest"],
                   "gbdt": models["gbdt"]}

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), dpi=150)

    for ax, (name, model) in zip(axes, tree_models.items()):
        importances = model.feature_importances_
        indices = np.argsort(importances)[::-1]
        sorted_features = [FEATURES[i] for i in indices]
        sorted_values = importances[indices]

        colors = [MODEL_COLORS[name]] * len(sorted_features)
        ax.barh(range(len(sorted_features) - 1, -1, -1), sorted_values,
                color=colors, alpha=0.85)
        ax.set_yticks(range(len(sorted_features) - 1, -1, -1))
        ax.set_yticklabels(sorted_features, fontsize=9)
        ax.set_xlabel("特征重要性", fontsize=11)
        ax.set_title(MODEL_LABELS[name], fontsize=12, fontweight="bold")
        ax.grid(alpha=0.2, axis="x")

    fig.suptitle("图4  随机森林与 GBDT 特征重要性对比", fontsize=14, fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    plt.savefig(OUT_FEATURE, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  [输出] 特征重要性: {OUT_FEATURE}")


def plot_pred_vs_actual(predictions, y_test):
    """绘制预测 vs 实际收益率散点图（随机森林）。"""
    # 用随机森林的预测做散点图
    pred = predictions["random_forest"]

    fig, ax = plt.subplots(figsize=(7, 6), dpi=150)
    ax.scatter(y_test * 100, pred * 100, s=8, alpha=0.25, color=MODEL_COLORS["random_forest"])
    # 理想线 y=x
    lim = max(abs(y_test).max(), abs(pred).max()) * 100 * 1.1
    ax.plot([-lim, lim], [-lim, lim], "--", color="red", linewidth=1.2, label="理想线 y=x")
    ax.axhline(y=0, color="gray", linewidth=0.5)
    ax.axvline(x=0, color="gray", linewidth=0.5)
    ax.set_xlabel("实际未来60日收益率 (%)", fontsize=12)
    ax.set_ylabel("模型预测收益率 (%)", fontsize=12)
    ax.set_title("图5  随机森林：预测收益率 vs 实际收益率", fontsize=13, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(alpha=0.2)
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    plt.tight_layout()
    plt.savefig(OUT_SCATTER, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  [输出] 预测散点图: {OUT_SCATTER}")


# ====================== 8. 数据字典 ======================
def save_meta(train, test, strategy_results, metrics_df):
    """保存数据字典 JSON。"""
    meta = {
        "task": "TASK6 — 智能决策者：用机器学习定制专属策略",
        "author": "张靖悦",
        "data": {
            "source": "Tushare Pro — 沪深300成分股日线数据",
            "date_range": f"{train['trade_date'].min().strftime('%Y-%m-%d')} ~ {test['trade_date'].max().strftime('%Y-%m-%d')}",
            "train_period": f"{train['trade_date'].min().strftime('%Y-%m-%d')} ~ {train['trade_date'].max().strftime('%Y-%m-%d')}",
            "test_period": f"{test['trade_date'].min().strftime('%Y-%m-%d')} ~ {test['trade_date'].max().strftime('%Y-%m-%d')}",
            "n_stocks": int(train["ts_code"].nunique()),
            "n_train_samples": int(len(train)),
            "n_test_samples": int(len(test)),
        },
        "features": {
            "动量类": ["ret_5d (5日收益)", "ret_20d (20日收益)", "ret_60d (60日收益)"],
            "波动率类": ["vol_20d (20日收益波动)", "vol_60d (60日收益波动)"],
            "量价类": ["turnover_5d (5日相对换手)", "turnover_20d (20日相对换手)",
                      "amount_log (对数成交额)", "range_20d (20日振幅)"],
            "技术类": ["ma_gap_5_20 (5/20日均线偏离)", "ma_gap_20_60 (20/60日均线偏离)",
                      "rsi_14 (14日RSI)", "volume_ratio (量比)"],
        },
        "target": "future_ret_60d — 未来60个交易日累计收益率（连续值，回归任务）",
        "strategy": {
            "type": "横截面选股 + 季度再平衡",
            "selection": f"每季度选模型预测收益最高的 Top-{TOP_K} 只等权持有",
            "rebalance": "每季度末调仓",
            "benchmark": "沪深300等权持有（不选股）",
        },
        "models": list(MODEL_LABELS.values()),
        "metrics_summary": metrics_df.to_dict("records"),
    }
    with open(OUT_META_JSON, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"  [输出] 数据字典: {OUT_META_JSON}")


# ====================== 主函数 ======================
def main():
    print("=" * 60)
    print("TASK6 智能决策者：用机器学习定制专属策略")
    print("=" * 60)

    # 1. 加载数据
    df = load_panel()

    # 2. 因子工程
    panel = build_factors(df)

    # 3. 切分
    train, test, X_train, X_test, y_train, y_test, scaler = split_data(panel)

    # 4. 训练 + 预测
    models, predictions = train_and_predict(X_train, y_train, X_test, y_test)

    # 5. 季度再平衡策略
    strategy_results = quarterly_topk_strategy(test, predictions, TOP_K)

    # 6. 回测指标
    metrics_df = calc_metrics(strategy_results)

    # 7. 绘图
    print("\n" + "=" * 60)
    print("步骤7：绘制图表")
    print("=" * 60)
    plot_nav_curves(strategy_results)
    plot_quarterly_returns(strategy_results)
    plot_drawdown(strategy_results)
    plot_feature_importance(models)
    plot_pred_vs_actual(predictions, y_test)

    # 8. 数据字典
    print("\n" + "=" * 60)
    print("步骤8：保存数据字典")
    print("=" * 60)
    save_meta(train, test, strategy_results, metrics_df)

    print("\n" + "=" * 60)
    print("所有产物已生成，TASK6 主脚本运行完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
