#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TASK5 AI交易引擎：机器学习算法与场景应用
=========================================

使用 scikit-learn 提供的乳腺癌诊断二分类数据集，演示并对比三类经典
分类机器学习算法——逻辑回归（Logistic Regression）、决策树
（Decision Tree）、随机森林（Random Forest）——在金融风控/信用评估
等二分类场景中的建模与评估流程。

本脚本完成以下工作：
  1. 加载 sklearn 内置的 load_breast_cancer 二分类数据集
  2. 对特征做 Z-Score 标准化，并按 7:3 划分训练集 / 测试集
  3. 构建并训练上述三类分类模型
  4. 计算混淆矩阵、精确率 / 召回率 / F1 / AUC，绘制 ROC 曲线
  5. 输出：
       - TASK5_三模型ROC曲线对比.png   （ROC 曲线叠加对比）
       - TASK5_混淆矩阵热力图.png        （三模型混淆矩阵子图）
       - TASK5_模型性能指标.csv          （性能指标对比表）

运行环境（隔离 venv）：
  python -m venv ... && pip install scikit-learn matplotlib pandas numpy

作者：张靖悦
"""

import os
import json
import numpy as np
import pandas as pd
import matplotlib
import matplotlib.font_manager as fm
matplotlib.use("Agg")  # 无界面环境后台出图
import matplotlib.pyplot as plt

# 注册系统中文字体，避免图表中文显示为方块
for _fp in (r"C:/Windows/Fonts/simhei.ttf", r"C:/Windows/Fonts/msyh.ttc"):
    if os.path.exists(_fp):
        try:
            fm.fontManager.addfont(_fp)
        except Exception:
            pass
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "SimSun", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

from sklearn.datasets import load_breast_cancer
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    confusion_matrix,
    classification_report,
    roc_curve,
    roc_auc_score,
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
)

# ====================== 全局配置 ======================
RANDOM_STATE = 42
TEST_SIZE = 0.30

# 输出目录（本文件同目录）
HERE = os.path.dirname(os.path.abspath(__file__))
ROC_PNG = os.path.join(HERE, "TASK5_三模型ROC曲线对比.png")
CM_PNG = os.path.join(HERE, "TASK5_混淆矩阵热力图.png")
CSV_PATH = os.path.join(HERE, "TASK5_模型性能指标.csv")
META_PATH = os.path.join(HERE, "TASK5_模型数据字典.json")

# 模型显示名称（与论文 / 报告一致）
MODEL_LABELS = {
    "logistic": "逻辑回归 (Logistic Regression)",
    "decision_tree": "决策树 (Decision Tree)",
    "random_forest": "随机森林 (Random Forest)",
}
# ROC 曲线配色
MODEL_COLORS = {
    "logistic": "#1f77b4",
    "decision_tree": "#ff7f0e",
    "random_forest": "#2ca02c",
}


def load_and_split():
    """加载乳腺癌数据集并完成标准化 + 训练/测试集划分。"""
    data = load_breast_cancer()
    X = data.data          # 特征矩阵 (569, 30)
    y = data.target        # 标签：0=恶性(malignant)，1=良性(benign)
    feature_names = list(data.feature_names)

    # Z-Score 标准化（仅对训练集 fit，再 transform 测试集，避免数据泄露）
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
        stratify=y,   # 保持正负样本比例一致
    )
    return {
        "X_train": X_train, "X_test": X_test,
        "y_train": y_train, "y_test": y_test,
        "feature_names": feature_names,
        "n_samples": int(X.shape[0]),
        "n_features": int(X.shape[1]),
        "target_names": list(data.target_names),
    }


def build_models():
    """构造三类分类器（固定随机种子，保证结果可复现）。"""
    return {
        "logistic": LogisticRegression(max_iter=1000, random_state=RANDOM_STATE),
        "decision_tree": DecisionTreeClassifier(max_depth=5, random_state=RANDOM_STATE),
        "random_forest": RandomForestClassifier(n_estimators=100, random_state=RANDOM_STATE),
    }


def evaluate(model, name, X_train, X_test, y_train, y_test):
    """训练 + 预测 + 评估，返回指标字典与绘图所需数据。"""
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    # 概率 / 决策函数 → 用于 ROC（统一取正类 "良性" 的得分）
    if hasattr(model, "predict_proba"):
        y_score = model.predict_proba(X_test)[:, 1]
    else:
        y_score = model.decision_function(X_test)

    cm = confusion_matrix(y_test, y_pred)
    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred)
    rec = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)
    auc = roc_auc_score(y_test, y_score)

    fpr, tpr, _ = roc_curve(y_test, y_score)

    print(f"\n===== {MODEL_LABELS[name]} =====")
    print(f"  准确率 Accuracy : {acc:.4f}")
    print(f"  精确率 Precision: {prec:.4f}")
    print(f"  召回率 Recall   : {rec:.4f}")
    print(f"  F1 分数        : {f1:.4f}")
    print(f"  AUC            : {auc:.4f}")
    print("  混淆矩阵 (行=真实, 列=预测):")
    print(f"           预测恶性  预测良性")
    print(f"  真实恶性   {cm[0][0]:5d}     {cm[0][1]:5d}")
    print(f"  真实良性   {cm[1][0]:5d}     {cm[1][1]:5d}")

    return {
        "name": name,
        "label": MODEL_LABELS[name],
        "color": MODEL_COLORS[name],
        "accuracy": acc,
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "auc": auc,
        "confusion_matrix": cm.tolist(),
        "fpr": fpr.tolist(),
        "tpr": tpr.tolist(),
    }


def plot_roc(results):
    """绘制三模型 ROC 曲线叠加对比图。"""
    plt.figure(figsize=(7.2, 6.0), dpi=150)

    for r in results:
        plt.plot(
            r["fpr"], r["tpr"],
            color=r["color"], lw=2.2,
            label=f"{r['label']}\n(AUC = {r['auc']:.3f})",
        )

    # 随机猜测基线
    plt.plot([0, 1], [0, 1], "--", color="#888888", lw=1.5, label="随机猜测 (AUC = 0.500)")

    plt.xlim([-0.02, 1.02])
    plt.ylim([-0.02, 1.02])
    plt.xlabel("假正率 FPR (False Positive Rate)", fontsize=12)
    plt.ylabel("真正率 TPR (True Positive Rate)", fontsize=12)
    plt.title("图1  三类分类模型 ROC 曲线对比", fontsize=14, fontweight="bold")
    plt.legend(loc="lower right", fontsize=9, framealpha=0.9)
    plt.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(ROC_PNG, dpi=150)
    plt.close()
    print(f"[输出] ROC 曲线已保存: {ROC_PNG}")


def plot_confusion_matrices(results):
    """绘制三模型混淆矩阵 1×3 子图热力图。"""
    n = len(results)
    fig, axes = plt.subplots(1, n, figsize=(5.2 * n, 4.6), dpi=150)
    if n == 1:
        axes = [axes]

    classes = ["恶性", "良性"]
    for ax, r in zip(axes, results):
        cm = np.array(r["confusion_matrix"])
        im = ax.imshow(cm, cmap="Blues", interpolation="nearest")
        ax.set_title(r["label"], fontsize=11, fontweight="bold")
        ax.set_xticks([0, 1]); ax.set_yticks([0, 1])
        ax.set_xticklabels(classes, fontsize=9)
        ax.set_yticklabels(classes, fontsize=9)
        ax.set_xlabel("预测标签", fontsize=9)
        ax.set_ylabel("真实标签", fontsize=9)

        # 在每个格子里标注数值
        thresh = cm.max() / 2.0
        for i in range(cm.shape[0]):
            for j in range(cm.shape[1]):
                ax.text(
                    j, i, format(cm[i, j], "d"),
                    ha="center", va="center",
                    color="white" if cm[i, j] > thresh else "black",
                    fontsize=13, fontweight="bold",
                )
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    fig.suptitle("图2  三类分类模型混淆矩阵热力图", fontsize=14, fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(CM_PNG, dpi=150)
    plt.close()
    print(f"[输出] 混淆矩阵已保存: {CM_PNG}")


def save_metrics_csv(results, meta):
    """保存性能指标对比表。"""
    rows = []
    for r in results:
        rows.append({
            "模型": r["label"],
            "准确率 Accuracy": round(r["accuracy"], 4),
            "精确率 Precision": round(r["precision"], 4),
            "召回率 Recall": round(r["recall"], 4),
            "F1 分数": round(r["f1"], 4),
            "AUC": round(r["auc"], 4),
        })
    df = pd.DataFrame(rows)
    df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    print(f"[输出] 指标表已保存: {CSV_PATH}")

    # 同时保存数据字典（供报告 / 看板引用）
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"[输出] 数据字典已保存: {META_PATH}")


def main():
    print("=" * 60)
    print("TASK5 机器学习分类建模与评估")
    print("=" * 60)

    meta = load_and_split()
    print(f"\n数据集: 乳腺癌诊断 (load_breast_cancer)")
    print(f"  样本数 n      : {meta['n_samples']}")
    print(f"  特征数 d      : {meta['n_features']}")
    print(f"  类别          : {meta['target_names']}  (0=恶性, 1=良性)")
    print(f"  训练 / 测试   : {len(meta['y_train'])} / {len(meta['y_test'])} "
          f"(test_size={TEST_SIZE})")

    models = build_models()
    results = []
    for name, mdl in models.items():
        res = evaluate(mdl, name, meta["X_train"], meta["X_test"],
                       meta["y_train"], meta["y_test"])
        results.append(res)

    # 按 AUC 降序排序，便于报告引用
    results_sorted = sorted(results, key=lambda x: x["auc"], reverse=True)
    print("\n===== 模型 AUC 排名 =====")
    for i, r in enumerate(results_sorted, 1):
        print(f"  {i}. {r['label']}  AUC={r['auc']:.4f}")

    plot_roc(results)
    plot_confusion_matrices(results)
    save_metrics_csv(results, {
        "dataset": "load_breast_cancer",
        "n_samples": meta["n_samples"],
        "n_features": meta["n_features"],
        "test_size": TEST_SIZE,
        "random_state": RANDOM_STATE,
        "target_names": meta["target_names"],
        "feature_names": meta["feature_names"],
        "results": [
            {k: v for k, v in r.items() if k not in ("fpr", "tpr")}
            for r in results
        ],
    })

    print("\n所有产物已生成，任务完成。")


if __name__ == "__main__":
    main()
