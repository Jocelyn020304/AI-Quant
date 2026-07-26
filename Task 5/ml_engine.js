/* ============================================================
 * ml_engine.js — 纯前端机器学习引擎（无后端依赖）
 * ------------------------------------------------------------
 * 提供：CSV 解析、数据标准化/归一化、分层抽样、六种分类算法
 *       （逻辑回归 / 决策树 / 随机森林 / K近邻 / 朴素贝叶斯 /
 *        线性 SVM）、混淆矩阵、精确率/召回率/F1、ROC/AUC
 *        （含多分类 One-vs-Rest）。
 *
 * 在浏览器中以全局变量 MLEngine 暴露；在 Node 中通过
 * module.exports 暴露，便于单元测试。
 * ============================================================ */

/* ---------- 基础工具 ---------- */

function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function shuffle(arr, rng) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    const tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
  }
  return arr;
}

function shuffleIdx(d, rng) {
  const a = []; for (let i = 0; i < d; i++) a.push(i);
  return shuffle(a, rng);
}

function identityMap(d) { const a = []; for (let i = 0; i < d; i++) a.push(i); return a; }

function argmax(arr) {
  let bi = 0, bv = -Infinity;
  for (let k = 0; k < arr.length; k++) if (arr[k] > bv) { bv = arr[k]; bi = k; }
  return bi;
}

function euclid(a, b) {
  let s = 0;
  for (let j = 0; j < a.length; j++) { const d = a[j] - b[j]; s += d * d; }
  return Math.sqrt(s);
}

/* ---------- CSV 解析（支持引号） ---------- */

function parseCSV(text) {
  text = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const rows = [];
  let i = 0, field = "", row = [], inQ = false;
  while (i < text.length) {
    const c = text[i];
    if (inQ) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; }
        else inQ = false;
      } else field += c;
    } else {
      if (c === '"') inQ = true;
      else if (c === ",") { row.push(field); field = ""; }
      else if (c === "\n") { row.push(field); rows.push(row); row = []; field = ""; }
      else if (c === ";") { row.push(field); field = ""; } // 容错：分号分隔
      else if (c === "\t") { row.push(field); field = ""; } // 容错：制表符
      else field += c;
    }
    i++;
  }
  if (field.length || row.length) { row.push(field); rows.push(row); }
  // 去掉完全空白的行
  return rows.filter(r => r.length && !(r.length === 1 && r[0].trim() === ""));
}

/* ---------- 标签编码 ---------- */

function encodeLabels(yRaw) {
  const uniq = [];
  const map = new Map();
  for (const v of yRaw) {
    if (!map.has(v)) { map.set(v, uniq.length); uniq.push(v); }
  }
  const y = yRaw.map(v => map.get(v));
  return { y, classes: uniq, K: uniq.length };
}

/* ---------- 预处理 ---------- */

function fitStandardize(X) {
  const d = X[0].length, n = X.length;
  const mean = new Array(d).fill(0), std = new Array(d).fill(0);
  for (let j = 0; j < d; j++) { let s = 0; for (let i = 0; i < n; i++) s += X[i][j]; mean[j] = s / n; }
  for (let j = 0; j < d; j++) { let s = 0; for (let i = 0; i < n; i++) { const dd = X[i][j] - mean[j]; s += dd * dd; } std[j] = Math.sqrt(s / n) || 1; }
  return {
    mean, std,
    transform(Xt) { return Xt.map(r => r.map((v, j) => std[j] ? (v - mean[j]) / std[j] : 0)); }
  };
}

function fitMinMax(X) {
  const d = X[0].length, n = X.length;
  const min = new Array(d).fill(Infinity), max = new Array(d).fill(-Infinity);
  for (let i = 0; i < n; i++) for (let j = 0; j < d; j++) {
    if (X[i][j] < min[j]) min[j] = X[i][j];
    if (X[i][j] > max[j]) max[j] = X[i][j];
  }
  return {
    min, max,
    transform(Xt) { return Xt.map(r => r.map((v, j) => { const rg = max[j] - min[j]; return rg ? (v - min[j]) / rg : 0; })); }
  };
}

/* ---------- 数据集划分（分层抽样） ---------- */

function trainTestSplit(n, yInt, { trainRatio = 0.7, seed = 42, stratified = true } = {}) {
  const rng = mulberry32(seed);
  const trainIdx = [], testIdx = [];
  if (stratified) {
    const groups = {};
    for (let i = 0; i < n; i++) (groups[yInt[i]] = groups[yInt[i]] || []).push(i);
    for (const k in groups) {
      const arr = groups[k]; shuffle(arr, rng);
      const m = Math.max(1, Math.floor(arr.length * trainRatio));
      trainIdx.push(...arr.slice(0, m));
      testIdx.push(...arr.slice(m));
    }
  } else {
    const arr = []; for (let i = 0; i < n; i++) arr.push(i);
    shuffle(arr, rng);
    const m = Math.floor(n * trainRatio);
    trainIdx.push(...arr.slice(0, m));
    testIdx.push(...arr.slice(m));
  }
  return { trainIdx, testIdx };
}

/* ---------- 评估指标 ---------- */

function confusionMatrix(yTrue, yPred, K) {
  const m = [];
  for (let a = 0; a < K; a++) m.push(new Array(K).fill(0));
  for (let i = 0; i < yTrue.length; i++) m[yTrue[i]][yPred[i]]++;
  return m;
}

function computeAUC(yBinary, scores) {
  const n = yBinary.length;
  if (n === 0) return 0.5;
  const order = []; for (let i = 0; i < n; i++) order.push(i);
  order.sort((a, b) => scores[a] - scores[b]);
  const rank = new Array(n);
  let i = 0;
  while (i < n) {
    let j = i;
    while (j + 1 < n && scores[order[j + 1]] === scores[order[i]]) j++;
    const avg = (i + j) / 2 + 1;
    for (let k = i; k <= j; k++) rank[order[k]] = avg;
    i = j + 1;
  }
  let pos = 0, neg = 0;
  for (let k = 0; k < n; k++) { if (yBinary[k] === 1) pos++; else neg++; }
  if (pos === 0 || neg === 0) return 0.5;
  let sumr = 0;
  for (let k = 0; k < n; k++) if (yBinary[k] === 1) sumr += rank[k];
  return (sumr - pos * (pos + 1) / 2) / (pos * neg);
}

function rocCurve(yBinary, scores) {
  const n = yBinary.length;
  const P = yBinary.reduce((a, b) => a + b, 0);
  const N = n - P;
  if (P === 0 || N === 0) return { fpr: [0, 1], tpr: [0, 1], auc: 0.5 };
  const order = []; for (let i = 0; i < n; i++) order.push(i);
  order.sort((a, b) => scores[b] - scores[a]);
  const pts = [[0, 0]];
  let tp = 0, fp = 0;
  for (const i of order) {
    if (yBinary[i] === 1) tp++; else fp++;
    pts.push([fp / N, tp / P]);
  }
  const uniq = [];
  for (const p of pts) {
    const last = uniq[uniq.length - 1];
    if (!last || last[0] !== p[0] || last[1] !== p[1]) uniq.push(p);
  }
  // 降采样，控制点数
  let fpr = uniq.map(p => p[0]), tpr = uniq.map(p => p[1]);
  if (fpr.length > 200) {
    const step = Math.ceil(fpr.length / 200);
    fpr = fpr.filter((_, idx) => idx % step === 0);
    tpr = tpr.filter((_, idx) => idx % step === 0);
    if (fpr[fpr.length - 1] !== 1) { fpr.push(1); tpr.push(1); }
  }
  return { fpr, tpr, auc: computeAUC(yBinary, scores) };
}

// 多分类 macro ROC：在固定 FPR 网格上插值各分类 OvR 的 TPR 再平均
function macroROC(yInt, yProba, K) {
  const n = yInt.length;
  const gridN = 100;
  const grid = [];
  for (let i = 0; i <= gridN; i++) grid.push(i / gridN);
  const perClassAUC = [];
  const interp = [];
  for (let c = 0; c < K; c++) {
    const yb = yInt.map(v => (v === c ? 1 : 0));
    const sc = yProba.map(p => p[c]);
    const roc = rocCurve(yb, sc);
    perClassAUC.push(roc.auc);
    // 线性插值到 grid
    const tprAt = new Array(gridN + 1).fill(0);
    let p = 0;
    for (let g = 0; g <= gridN; g++) {
      const f = grid[g];
      while (p < roc.fpr.length - 1 && roc.fpr[p + 1] < f) p++;
      const f0 = roc.fpr[p], f1 = roc.fpr[Math.min(p + 1, roc.fpr.length - 1)];
      const t0 = roc.tpr[p], t1 = roc.tpr[Math.min(p + 1, roc.tpr.length - 1)];
      if (f1 === f0) tprAt[g] = t1;
      else tprAt[g] = t0 + (t1 - t0) * (f - f0) / (f1 - f0);
    }
    interp.push(tprAt);
  }
  const macroTpr = grid.map((_, g) => {
    let s = 0; for (let c = 0; c < K; c++) s += interp[c][g]; return s / K;
  });
  const macroAuc = perClassAUC.reduce((a, b) => a + b, 0) / K;
  return { fpr: grid, tpr: macroTpr, auc: macroAuc };
}

function computeMetrics(yTrue, yPred, yProba, K, positiveIdx) {
  const cm = confusionMatrix(yTrue, yPred, K);
  let correct = 0;
  for (let i = 0; i < yTrue.length; i++) if (yTrue[i] === yPred[i]) correct++;
  const acc = correct / yTrue.length;
  let pSum = 0, rSum = 0, fSum = 0;
  for (let c = 0; c < K; c++) {
    let tp = cm[c][c], fp = 0, fn = 0;
    for (let j = 0; j < K; j++) { if (j !== c) { fp += cm[j][c]; fn += cm[c][j]; } }
    const prec = (tp + fp) > 0 ? tp / (tp + fp) : 0;
    const rec = (tp + fn) > 0 ? tp / (tp + fn) : 0;
    const f1 = (prec + rec) > 0 ? 2 * prec * rec / (prec + rec) : 0;
    pSum += prec; rSum += rec; fSum += f1;
  }
  const macroP = pSum / K, macroR = rSum / K, macroF = fSum / K;
  const scores = yProba.map(p => p[positiveIdx]);
  const auc = computeAUC(yTrue.map(v => (v === positiveIdx ? 1 : 0)), scores);
  return { cm, acc, macroP, macroR, macroF, auc, positiveIdx };
}

/* ---------- 算法实现 ---------- */

// 逻辑回归（批量梯度下降 + L2）
function trainLogisticRegression(X, yInt, { lr = 0.1, iters = 300, C = 1.0 } = {}, K) {
  const n = X.length, d = X[0].length;
  const pos = K > 1 ? 1 : 0;
  const y = yInt.map(v => (v === pos ? 1 : 0));
  const Xb = X.map(r => [1, ...r]);
  const dd = d + 1;
  let w = new Array(dd).fill(0);
  const lambda = 1 / (C * n);
  for (let it = 0; it < iters; it++) {
    const grad = new Array(dd).fill(0);
    for (let i = 0; i < n; i++) {
      let z = 0; for (let j = 0; j < dd; j++) z += w[j] * Xb[i][j];
      const p = 1 / (1 + Math.exp(-z));
      const err = p - y[i];
      for (let j = 0; j < dd; j++) grad[j] += err * Xb[i][j];
    }
    for (let j = 0; j < dd; j++) {
      const reg = j === 0 ? 0 : lambda * w[j];
      w[j] -= lr * (grad[j] / n + reg);
    }
  }
  return {
    name: "逻辑回归",
    predictProba(Xt) {
      return Xt.map(r => {
        let z = w[0]; for (let j = 0; j < d; j++) z += w[j + 1] * r[j];
        const p = 1 / (1 + Math.exp(-z));
        return [1 - p, p];
      });
    }
  };
}

// CART 决策树（基尼系数）
function buildCART(X, yInt, featMap, { maxDepth = 10, minSplit = 10 } = {}, K) {
  function gini(counts, n) {
    if (n === 0) return 0;
    let s = 0; for (let k = 0; k < K; k++) { const p = counts[k] / n; s += p * p; }
    return 1 - s;
  }
  function countClasses(idxs) {
    const c = new Array(K).fill(0);
    for (const i of idxs) c[yInt[i]]++;
    return c;
  }
  function build(idxs, depth) {
    const counts = countClasses(idxs);
    const n = idxs.length;
    let nonzero = 0; for (const c of counts) if (c > 0) nonzero++;
    if (depth >= maxDepth || n < minSplit || nonzero <= 1) return { leaf: true, dist: counts, n };
    let best = null;
    const dlocal = featMap.length;
    for (let f = 0; f < dlocal; f++) {
      const gf = featMap[f];
      const vals = idxs.map(i => X[i][gf]);
      const uniq = [...new Set(vals)].sort((a, b) => a - b);
      let ths = [];
      for (let k = 0; k < uniq.length - 1; k++) ths.push((uniq[k] + uniq[k + 1]) / 2);
      if (ths.length > 25) {
        const st = Math.ceil(ths.length / 25);
        const nt = []; for (let k = 0; k < ths.length; k += st) nt.push(ths[k]);
        ths = nt;
      }
      for (const t of ths) {
        let l = 0, r = 0;
        const lc = new Array(K).fill(0), rc = new Array(K).fill(0);
        for (const i of idxs) {
          if (X[i][gf] <= t) { lc[yInt[i]]++; l++; }
          else { rc[yInt[i]]++; r++; }
        }
        if (l === 0 || r === 0) continue;
        const wg = (l / n) * gini(lc, l) + (r / n) * gini(rc, r);
        if (best === null || wg < best.g) best = { g: wg, f, t, lc, rc };
      }
    }
    if (best === null) return { leaf: true, dist: counts, n };
    const li = [], ri = [];
    for (const i of idxs) { if (X[i][featMap[best.f]] <= best.t) li.push(i); else ri.push(i); }
    return { leaf: false, f: best.f, t: best.t, left: build(li, depth + 1), right: build(ri, depth + 1), dist: counts, n };
  }
  const root = build([...Array(X.length).keys()], 0);
  function traverse(r) {
    let node = root;
    while (!node.leaf) node = (r[featMap[node.f]] <= node.t) ? node.left : node.right;
    return node.dist;
  }
  return {
    predict(Xt) {
      return Xt.map(r => {
        const d = traverse(r);
        return argmax(d);
      });
    },
    predictProba(Xt) {
      return Xt.map(r => {
        const d = traverse(r);
        const s = d.reduce((a, b) => a + b, 0) || 1;
        return d.map(c => c / s);
      });
    }
  };
}

// 随机森林（CART + Bagging + 特征子采样）
function trainRandomForest(X, yInt, { nTrees = 100, maxDepth = 12, minSplit = 10, mtry = null } = {}, K, rng) {
  const n = X.length, d = X[0].length;
  const mtry_ = mtry || Math.max(1, Math.floor(Math.sqrt(d)));
  const trees = [];
  for (let t = 0; t < nTrees; t++) {
    const idx = []; for (let i = 0; i < n; i++) idx.push(Math.floor(rng() * n));
    const feats = shuffleIdx(d, rng).slice(0, mtry_);
    trees.push(buildCART(X, yInt, feats, { maxDepth, minSplit }, K));
  }
  return {
    name: "随机森林",
    predictProba(Xt) {
      return Xt.map(x => {
        const sums = new Array(K).fill(0);
        for (const tree of trees) {
          const d = tree.predictProba([x])[0];
          for (let k = 0; k < K; k++) sums[k] += d[k];
        }
        return sums.map(v => v / trees.length);
      });
    }
  };
}

// K 近邻
function trainKNN(X, yInt, { k = 5 } = {}, K) {
  return {
    name: "K近邻",
    predictProba(Xt) {
      return Xt.map(x => {
        const dists = X.map((r, i) => ({ i, d: euclid(x, r) }));
        dists.sort((a, b) => a.d - b.d);
        const top = dists.slice(0, k);
        const cnt = new Array(K).fill(0);
        for (const o of top) cnt[yInt[o.i]]++;
        return cnt.map(c => c / k);
      });
    }
  };
}

// 高斯朴素贝叶斯
function trainGaussianNB(X, yInt, {} = {}, K) {
  const d = X[0].length, n = X.length;
  const stats = [];
  for (let c = 0; c < K; c++) stats.push({ mean: new Array(d).fill(0), var: new Array(d).fill(0), prior: 0, cnt: 0 });
  for (let i = 0; i < n; i++) {
    const s = stats[yInt[i]];
    s.cnt++;
    for (let j = 0; j < d; j++) s.mean[j] += X[i][j];
  }
  for (const s of stats) { for (let j = 0; j < d; j++) s.mean[j] /= s.cnt; s.prior = s.cnt / n; }
  for (let i = 0; i < n; i++) {
    const s = stats[yInt[i]];
    for (let j = 0; j < d; j++) { const diff = X[i][j] - s.mean[j]; s.var[j] += diff * diff; }
  }
  const eps = 1e-9;
  for (const s of stats) for (let j = 0; j < d; j++) s.var[j] = (s.var[j] + eps) / s.cnt;
  return {
    name: "朴素贝叶斯",
    predictProba(Xt) {
      return Xt.map(x => {
        const logp = new Array(K).fill(0);
        for (let c = 0; c < K; c++) {
          const s = stats[c];
          logp[c] = Math.log(s.prior + 1e-12);
          for (let j = 0; j < d; j++) {
            const v = s.var[j];
            const diff = x[j] - s.mean[j];
            logp[c] += -0.5 * Math.log(2 * Math.PI * v) - diff * diff / (2 * v);
          }
        }
        const mx = Math.max(...logp);
        const ex = logp.map(v => Math.exp(v - mx));
        const sum = ex.reduce((a, b) => a + b, 0);
        return ex.map(v => v / sum);
      });
    }
  };
}

// 线性 SVM（Pegasos 随机梯度下降，hinge loss）
function trainLinearSVM(X, yInt, { iters = 2000, lambda = 0.01 } = {}, K) {
  const n = X.length, d = X[0].length;
  const pos = K > 1 ? 1 : 0;
  const yb = yInt.map(v => (v === pos ? 1 : -1));
  let w = new Array(d).fill(0), b = 0;
  for (let t = 1; t <= iters; t++) {
    const i = Math.floor((t * 2654435761) % n);
    const lr = 1 / (lambda * t);
    const xi = X[i];
    let z = b; for (let j = 0; j < d; j++) z += w[j] * xi[j];
    if (yb[i] * z < 1) {
      for (let j = 0; j < d; j++) w[j] = w[j] * (1 - lr * lambda) + lr * yb[i] * xi[j];
      b += lr * yb[i];
    } else {
      for (let j = 0; j < d; j++) w[j] *= (1 - lr * lambda);
    }
  }
  return {
    name: "支持向量机",
    predictProba(Xt) {
      return Xt.map(x => {
        let z = b; for (let j = 0; j < d; j++) z += w[j] * x[j];
        const p = 1 / (1 + Math.exp(-z));
        return [1 - p, p];
      });
    }
  };
}

/* ---------- 模型注册表 ---------- */

const MODEL_REGISTRY = {
  lr: { label: "逻辑回归", train: (X, y, K, rng, o) => trainLogisticRegression(X, y, o, K) },
  dt: { label: "决策树", train: (X, y, K, rng, o) => { const m = buildCART(X, y, identityMap(X[0].length), o, K); m.name = "决策树"; return m; } },
  rf: { label: "随机森林", train: (X, y, K, rng, o) => trainRandomForest(X, y, o, K, rng) },
  knn: { label: "K近邻", train: (X, y, K, rng, o) => trainKNN(X, y, o, K) },
  nb: { label: "朴素贝叶斯", train: (X, y, K, rng, o) => trainGaussianNB(X, y, o, K) },
  svm: { label: "支持向量机", train: (X, y, K, rng, o) => trainLinearSVM(X, y, o, K) }
};

/* ---------- 示例数据生成（合成二分类） ---------- */

function generateExampleCSV() {
  const rng = mulberry32(7);
  const n = 600, d = 8;
  const header = ["f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "label"];
  const rows = [header.join(",")];
  const mu1 = [1.5, 1.2, -1.3, 0.8, 1.0, 1.4, -0.9, 1.1];
  function gauss() {
    let u = 0, v = 0;
    while (u === 0) u = rng();
    while (v === 0) v = rng();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }
  for (let i = 0; i < n; i++) {
    const cls = i % 2;
    const r = [];
    for (let j = 0; j < d; j++) {
      const mu = cls ? mu1[j] : 0;
      r.push((mu + gauss() * 0.8).toFixed(4));
    }
    r.push(cls);
    rows.push(r.join(","));
  }
  return rows.join("\n");
}

/* ---------- 导出 ---------- */

const MLEngine = {
  parseCSV, encodeLabels, fitStandardize, fitMinMax, trainTestSplit,
  computeMetrics, rocCurve, macroROC, confusionMatrix, computeAUC,
  MODEL_REGISTRY, generateExampleCSV, mulberry32
};

if (typeof module !== "undefined" && module.exports) {
  module.exports = MLEngine;
}
if (typeof window !== "undefined") {
  window.MLEngine = MLEngine;
}
