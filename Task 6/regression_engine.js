/* ============================================================
 * regression_engine.js — 纯前端机器学习回归引擎
 * ------------------------------------------------------------
 * 提供：面板数据因子计算、按日期切分、标准化、四种回归算法
 *       （Ridge / 决策树 / 随机森林 / KNN）、季度再平衡回测、
 *       回归评估指标（R²/MSE/方向准确率）、回测指标
 *       （累计收益/年化/夏普/MDD/胜率）。
 *
 * 在浏览器中以全局变量 RegEngine 暴露。
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

function euclid(a, b) {
  let s = 0;
  for (let j = 0; j < a.length; j++) { const d = a[j] - b[j]; s += d * d; }
  return Math.sqrt(s);
}

/* ---------- 矩阵运算 ---------- */

function transpose(M) {
  const r = M.length, c = M[0].length;
  const T = [];
  for (let j = 0; j < c; j++) {
    T.push([]);
    for (let i = 0; i < r; i++) T[j].push(M[i][j]);
  }
  return T;
}

function matMul(A, B) {
  const ar = A.length, ac = A[0].length, bc = B[0].length;
  const C = [];
  for (let i = 0; i < ar; i++) {
    C.push(new Array(bc).fill(0));
    for (let j = 0; j < bc; j++) {
      let s = 0;
      for (let k = 0; k < ac; k++) s += A[i][k] * B[k][j];
      C[i][j] = s;
    }
  }
  return C;
}

function matVec(A, v) {
  return A.map(row => row.reduce((s, val, j) => s + val * v[j], 0));
}

function matrixInverse(M) {
  const n = M.length;
  const aug = M.map((row, i) => [...row, ...Array(n).fill(0).map((_, j) => i === j ? 1 : 0)]);
  for (let i = 0; i < n; i++) {
    let maxRow = i;
    for (let k = i + 1; k < n; k++) {
      if (Math.abs(aug[k][i]) > Math.abs(aug[maxRow][i])) maxRow = k;
    }
    [aug[i], aug[maxRow]] = [aug[maxRow], aug[i]];
    if (Math.abs(aug[i][i]) < 1e-12) return null;
    const pivot = aug[i][i];
    for (let j = 0; j < 2 * n; j++) aug[i][j] /= pivot;
    for (let k = 0; k < n; k++) {
      if (k === i) continue;
      const factor = aug[k][i];
      for (let j = 0; j < 2 * n; j++) aug[k][j] -= factor * aug[i][j];
    }
  }
  return aug.map(row => row.slice(n));
}

/* ---------- 因子定义 ---------- */

const FACTOR_DEFS = [
  { key: "ret_5d",       name: "5日收益率",       group: "动量" },
  { key: "ret_20d",      name: "20日收益率",      group: "动量" },
  { key: "ret_60d",      name: "60日收益率",      group: "动量" },
  { key: "vol_20d",      name: "20日波动率",      group: "波动率" },
  { key: "vol_60d",      name: "60日波动率",      group: "波动率" },
  { key: "turnover_5d",  name: "5日均量比",       group: "量价" },
  { key: "turnover_20d", name: "20日均量比",      group: "量价" },
  { key: "amount_log",   name: "成交额对数",      group: "量价" },
  { key: "range_20d",    name: "20日振幅",        group: "量价" },
  { key: "ma_gap_5_20",  name: "5/20日均线偏离",   group: "技术" },
  { key: "ma_gap_20_60", name: "20/60日均线偏离",  group: "技术" },
  { key: "rsi_14",       name: "RSI(14)",         group: "技术" },
  { key: "volume_ratio", name: "量比",            group: "技术" },
];

/* ---------- 因子计算引擎 ---------- */
/* 输入：dailyData = { "000001.SZ": [{ts_code,trade_date,open,high,low,close,vol,amount}, ...], ... }
 * 输出：panel = [{ts_code, trade_date, ret_5d, ..., future_ret_60d}, ...]
 */

function computeFactors(dailyData, selectedKeys, forecastWindow = 60) {
  const panel = [];
  const allFeatureKeys = selectedKeys || FACTOR_DEFS.map(f => f.key);

  for (const code in dailyData) {
    const rows = dailyData[code];
    if (!rows || rows.length < 65) continue;

    // 确保按日期升序
    const sorted = [...rows].sort((a, b) => a.trade_date < b.trade_date ? -1 : 1);
    const n = sorted.length;
    const closes = sorted.map(r => r.close);
    const highs = sorted.map(r => r.high);
    const lows = sorted.map(r => r.low);
    const vols = sorted.map(r => r.vol);
    const amounts = sorted.map(r => r.amount);

    // 日收益率序列
    const dailyRet = [0];
    for (let i = 1; i < n; i++) dailyRet.push(closes[i] / closes[i - 1] - 1);

    // MA 辅助
    function ma(arr, period, idx) {
      if (idx < period - 1) return null;
      let s = 0;
      for (let i = idx - period + 1; i <= idx; i++) s += arr[i];
      return s / period;
    }

    function std(arr, period, idx) {
      if (idx < period - 1) return null;
      const m = ma(arr, period, idx);
      let s = 0;
      for (let i = idx - period + 1; i <= idx; i++) s += (arr[i] - m) ** 2;
      return Math.sqrt(s / period);
    }

    function maxArr(arr, period, idx) {
      if (idx < period - 1) return null;
      let m = -Infinity;
      for (let i = idx - period + 1; i <= idx; i++) if (arr[i] > m) m = arr[i];
      return m;
    }

    function minArr(arr, period, idx) {
      if (idx < period - 1) return null;
      let m = Infinity;
      for (let i = idx - period + 1; i <= idx; i++) if (arr[i] < m) m = arr[i];
      return m;
    }

    // RSI(14)
    function rsi(period, idx) {
      if (idx < period) return null;
      let gain = 0, loss = 0;
      for (let i = idx - period + 1; i <= idx; i++) {
        const ch = dailyRet[i];
        if (ch > 0) gain += ch; else loss -= ch;
      }
      const avgGain = gain / period, avgLoss = loss / period;
      if (avgLoss === 0) return 100;
      return 100 - 100 / (1 + avgGain / avgLoss);
    }

    // 从第 60 天开始（确保 60 日因子可用）
    for (let t = 59; t < n; t++) {
      const row = {
        ts_code: code,
        trade_date: sorted[t].trade_date,
        close: closes[t],
      };

      if (allFeatureKeys.includes("ret_5d"))      row.ret_5d = closes[t] / closes[t - 5] - 1;
      if (allFeatureKeys.includes("ret_20d"))      row.ret_20d = closes[t] / closes[t - 20] - 1;
      if (allFeatureKeys.includes("ret_60d"))     row.ret_60d = closes[t] / closes[t - 60] - 1;
      if (allFeatureKeys.includes("vol_20d"))      row.vol_20d = std(dailyRet, 20, t);
      if (allFeatureKeys.includes("vol_60d"))      row.vol_60d = std(dailyRet, 60, t);
      if (allFeatureKeys.includes("turnover_5d"))  row.turnover_5d = ma(vols, 5, t) / ma(vols, 20, t);
      if (allFeatureKeys.includes("turnover_20d")) row.turnover_20d = ma(vols, 20, t) / ma(vols, 60, t);
      if (allFeatureKeys.includes("amount_log"))   row.amount_log = Math.log(amounts[t] + 1);
      if (allFeatureKeys.includes("range_20d"))     row.range_20d = (maxArr(highs, 20, t) - minArr(lows, 20, t)) / closes[t];
      if (allFeatureKeys.includes("ma_gap_5_20"))   row.ma_gap_5_20 = ma(closes, 5, t) / ma(closes, 20, t) - 1;
      if (allFeatureKeys.includes("ma_gap_20_60"))  row.ma_gap_20_60 = ma(closes, 20, t) / ma(closes, 60, t) - 1;
      if (allFeatureKeys.includes("rsi_14"))        row.rsi_14 = rsi(14, t);
      if (allFeatureKeys.includes("volume_ratio"))  row.volume_ratio = vols[t] / ma(vols, 20, t);

      // 应变量：未来 N 日累计收益率
      if (t + forecastWindow < n) {
        row.future_ret = closes[t + forecastWindow] / closes[t] - 1;
      }

      panel.push(row);
    }
  }

  return panel;
}

/* ---------- 数据切分（按日期） ---------- */

function timeSplit(panel, splitDate) {
  const train = panel.filter(r => r.trade_date <= splitDate && r.future_ret !== undefined);
  const test  = panel.filter(r => r.trade_date > splitDate);
  return { train, test };
}

/* ---------- 标准化 ---------- */

function fitStandardize(X) {
  const n = X.length, d = X[0].length;
  const mean = new Array(d).fill(0);
  const std = new Array(d).fill(0);
  for (let i = 0; i < n; i++) for (let j = 0; j < d; j++) mean[j] += X[i][j];
  for (let j = 0; j < d; j++) mean[j] /= n;
  for (let i = 0; i < n; i++) for (let j = 0; j < d; j++) std[j] += (X[i][j] - mean[j]) ** 2;
  for (let j = 0; j < d; j++) std[j] = Math.sqrt(std[j] / n) || 1e-8;
  return {
    transform(Xt) {
      return Xt.map(r => r.map((v, j) => (v - mean[j]) / std[j]));
    }
  };
}

function fitMinMax(X) {
  const n = X.length, d = X[0].length;
  const min = new Array(d).fill(Infinity);
  const max = new Array(d).fill(-Infinity);
  for (let i = 0; i < n; i++) for (let j = 0; j < d; j++) {
    if (X[i][j] < min[j]) min[j] = X[i][j];
    if (X[i][j] > max[j]) max[j] = X[i][j];
  }
  const range = max.map((mx, j) => (mx - min[j]) || 1e-8);
  return {
    transform(Xt) {
      return Xt.map(r => r.map((v, j) => (v - min[j]) / range[j]));
    }
  };
}

/* ---------- Ridge 回归（闭式解） ---------- */

function trainRidge(X, y, { alpha = 1.0 } = {}) {
  const n = X.length, d = X[0].length;
  // 加截距列
  const Xb = X.map(r => [1, ...r]);
  const dd = d + 1;
  // X'X
  const Xt = transpose(Xb);
  const XtX = matMul(Xt, Xb);
  // L2 正则（不惩罚截距）
  for (let i = 1; i < dd; i++) XtX[i][i] += alpha;
  // X'y
  const Xty = matVec(Xt, y);
  // 求解 (X'X + λI)^{-1} X'y
  const inv = matrixInverse(XtX);
  let w;
  if (inv) {
    w = matVec(inv, Xty);
  } else {
    // 奇异矩阵 fallback：用均值
    const yMean = y.reduce((a, b) => a + b, 0) / n;
    w = [yMean, ...new Array(d).fill(0)];
  }
  return {
    name: "Ridge回归",
    predict(Xt) {
      return Xt.map(x => {
        let s = w[0];
        for (let j = 0; j < d; j++) s += w[j + 1] * x[j];
        return s;
      });
    },
    featureImportance() {
      return w.slice(1).map((v, i) => Math.abs(v));
    }
  };
}

/* ---------- 回归决策树（MSE 分裂） ---------- */

function buildRegressionTree(X, y, featMap, { maxDepth = 8, minSplit = 10 } = {}) {
  function mse(idxs) {
    if (idxs.length === 0) return 0;
    let m = 0;
    for (const i of idxs) m += y[i];
    m /= idxs.length;
    let s = 0;
    for (const i of idxs) s += (y[i] - m) ** 2;
    return s / idxs.length;
  }

  function meanY(idxs) {
    if (idxs.length === 0) return 0;
    let s = 0;
    for (const i of idxs) s += y[i];
    return s / idxs.length;
  }

  function build(idxs, depth) {
    const n = idxs.length;
    if (depth >= maxDepth || n < minSplit) return { leaf: true, val: meanY(idxs) };

    let best = null;
    const dlocal = featMap.length;
    for (let fi = 0; fi < dlocal; fi++) {
      const gf = featMap[fi];
      const vals = idxs.map(i => X[i][gf]);
      const uniq = [...new Set(vals)].sort((a, b) => a - b);
      let ths = [];
      for (let k = 0; k < uniq.length - 1; k++) ths.push((uniq[k] + uniq[k + 1]) / 2);
      if (ths.length > 25) {
        const st = Math.ceil(ths.length / 25);
        const nt = []; for (let k = 0; k < ths.length; k += st) nt.push(ths[k]);
        ths = nt;
      }
      const parentMSE = mse(idxs);
      for (const t of ths) {
        const li = [], ri = [];
        for (const i of idxs) {
          if (X[i][gf] <= t) li.push(i); else ri.push(i);
        }
        if (li.length === 0 || ri.length === 0) continue;
        const wg = (li.length / n) * mse(li) + (ri.length / n) * mse(ri);
        const gain = parentMSE - wg;
        if (best === null || gain > best.gain) best = { gain, f: fi, t, li, ri };
      }
    }
    if (best === null || best.gain <= 0) return { leaf: true, val: meanY(idxs) };
    return {
      leaf: false,
      f: best.f,
      t: best.t,
      left: build(best.li, depth + 1),
      right: build(best.ri, depth + 1)
    };
  }

  const root = build([...Array(X.length).keys()], 0);

  function traverse(r) {
    let node = root;
    while (!node.leaf) node = (r[featMap[node.f]] <= node.t) ? node.left : node.right;
    return node.val;
  }

  return {
    name: "决策树回归",
    predict(Xt) { return Xt.map(r => traverse(r)); },
    featureImportance() {
      const imp = new Array(X[0].length).fill(0);
      function count(node, depth) {
        if (!node.leaf) {
          imp[featMap[node.f]] += 1;
          count(node.left, depth + 1);
          count(node.right, depth + 1);
        }
      }
      count(root, 0);
      return imp;
    }
  };
}

/* ---------- 随机森林回归（Bagging + 特征子采样） ---------- */

function trainRegressionForest(X, y, { nTrees = 80, maxDepth = 8, minSplit = 10, mtry = null } = {}, rng) {
  const n = X.length, d = X[0].length;
  const mtry_ = mtry || Math.max(1, Math.floor(Math.sqrt(d)));
  const trees = [];
  for (let t = 0; t < nTrees; t++) {
    const idx = [];
    for (let i = 0; i < n; i++) idx.push(Math.floor(rng() * n));
    const feats = shuffleIdx(d, rng).slice(0, mtry_);
    trees.push(buildRegressionTree(X, y, feats, { maxDepth, minSplit }));
  }
  return {
    name: "随机森林回归",
    predict(Xt) {
      return Xt.map(x => {
        let s = 0;
        for (const tree of trees) s += tree.predict([x])[0];
        return s / trees.length;
      });
    },
    featureImportance() {
      const imp = new Array(d).fill(0);
      for (const tree of trees) {
        const ti = tree.featureImportance();
        for (let j = 0; j < d; j++) imp[j] += ti[j];
      }
      return imp.map(v => v / trees.length);
    }
  };
}

/* ---------- KNN 回归 ---------- */

function trainKNNRegressor(X, y, { k = 7 } = {}) {
  return {
    name: "KNN回归",
    predict(Xt) {
      return Xt.map(x => {
        const dists = X.map((r, i) => ({ i, d: euclid(x, r) }));
        dists.sort((a, b) => a.d - b.d);
        const top = dists.slice(0, Math.min(k, dists.length));
        // 距离加权平均
        let ws = 0, wv = 0;
        for (const o of top) {
          const w = 1 / (o.d + 1e-8);
          ws += w;
          wv += w * y[o.i];
        }
        return wv / ws;
      });
    },
    featureImportance() { return new Array(X[0].length).fill(0); }
  };
}

/* ---------- 模型注册表 ---------- */

const MODEL_REGISTRY = {
  ridge: { label: "Ridge回归", train: (X, y, rng, o) => trainRidge(X, y, o) },
  dt:    { label: "决策树回归", train: (X, y, rng, o) => buildRegressionTree(X, y, identityMap(X[0].length), o) },
  rf:    { label: "随机森林回归", train: (X, y, rng, o) => trainRegressionForest(X, y, o, rng) },
  knn:   { label: "KNN回归", train: (X, y, rng, o) => trainKNNRegressor(X, y, o) },
};

/* ---------- 回测引擎：季度再平衡 + Top-K 选股 ---------- */
/* 输入：
 *   testPanel: 测试集面板数据（含因子 + 可选 future_ret）
 *   model: 训练好的模型
 *   dailyData: 原始日线数据（用于计算实际持仓收益）
 *   featureKeys: 因子列表
 *   options: { topK, scaler }
 * 输出：{ nav, drawdown, quarterlyReturns, holdings, metrics }
 */

function quarterlyBacktest(testPanel, model, dailyData, featureKeys, { topK = 30, scaler = null } = {}) {
  // 提取所有日期并排序
  const allDates = [...new Set(testPanel.map(r => r.trade_date))].sort();

  // 按季度分组，取每季度第一个交易日作为调仓日
  const quarters = {};
  for (const date of allDates) {
    const y = date.substring(0, 4);
    const m = parseInt(date.substring(5, 7));
    const q = `${y}-Q${Math.ceil(m / 3)}`;
    if (!quarters[q]) quarters[q] = date; // 第一个交易日
  }
  const rebalanceDates = Object.values(quarters).sort();

  const navPoints = [];
  const drawdownPoints = [];
  const quarterlyReturns = [];
  const holdingsLog = [];
  let nav = 1.0;
  let peak = 1.0;

  navPoints.push({ date: rebalanceDates[0], nav: 1.0 });

  for (let q = 0; q < rebalanceDates.length; q++) {
    const rebDate = rebalanceDates[q];
    const nextRebDate = rebalanceDates[q + 1];

    // 获取调仓日所有股票的因子
    const dayRows = testPanel.filter(r => r.trade_date === rebDate);
    if (dayRows.length === 0) continue;

    // 提取特征矩阵
    let XDay = dayRows.map(r => featureKeys.map(k => r[k]));
    if (scaler) XDay = scaler.transform(XDay);

    // 模型预测
    const preds = model.predict(XDay);

    // 排序选 Top-K
    const ranked = dayRows.map((r, i) => ({
      ts_code: r.ts_code,
      pred: preds[i],
      close: r.close
    })).sort((a, b) => b.pred - a.pred);

    const topStocks = ranked.slice(0, Math.min(topK, ranked.length));
    holdingsLog.push({ date: rebDate, stocks: topStocks.map(s => ({ code: s.ts_code, pred: s.pred })) });

    // 如果有下一个调仓日，计算持仓收益
    if (nextRebDate) {
      let portRet = 0;
      let validCount = 0;
      for (const s of topStocks) {
        const stockData = dailyData[s.ts_code];
        if (!stockData) continue;
        const buyRow = stockData.find(r => r.trade_date === rebDate);
        const sellRow = stockData.find(r => r.trade_date === nextRebDate);
        if (buyRow && sellRow && buyRow.close > 0) {
          const ret = sellRow.close / buyRow.close - 1;
          portRet += ret;
          validCount++;
        }
      }
      if (validCount > 0) {
        portRet /= validCount;
        nav *= (1 + portRet);
        quarterlyReturns.push({
          quarter: Object.keys(quarters)[q],
          return: portRet,
          nav: nav
        });
        if (nav > peak) peak = nav;
        const dd = (nav - peak) / peak;
        navPoints.push({ date: nextRebDate, nav: nav });
        drawdownPoints.push({ date: nextRebDate, drawdown: dd });
      }
    }
  }

  // 基准：所有股票等权
  const benchmarkNav = [1.0];
  for (let q = 0; q < rebalanceDates.length - 1; q++) {
    const rebDate = rebalanceDates[q];
    const nextRebDate = rebalanceDates[q + 1];
    const dayRows = testPanel.filter(r => r.trade_date === rebDate);
    let benchRet = 0, cnt = 0;
    for (const r of dayRows) {
      const stockData = dailyData[r.ts_code];
      if (!stockData) continue;
      const buyRow = stockData.find(rr => rr.trade_date === rebDate);
      const sellRow = stockData.find(rr => rr.trade_date === nextRebDate);
      if (buyRow && sellRow && buyRow.close > 0) {
        benchRet += sellRow.close / buyRow.close - 1;
        cnt++;
      }
    }
    if (cnt > 0) {
      benchRet /= cnt;
      benchmarkNav.push(benchmarkNav[benchmarkNav.length - 1] * (1 + benchRet));
    } else {
      benchmarkNav.push(benchmarkNav[benchmarkNav.length - 1]);
    }
  }

  return {
    nav: navPoints,
    drawdown: drawdownPoints,
    quarterlyReturns,
    holdings: holdingsLog,
    benchmarkNav: navPoints.map((p, i) => ({ date: p.date, nav: benchmarkNav[i] || 1.0 })),
    rebalanceDates
  };
}

/* ---------- 回测指标计算 ---------- */

function computeBacktestMetrics(nav, quarterlyReturns, benchmarkNav) {
  const n = nav.length;
  if (n < 2) return { totalReturn: 0, annualReturn: 0, annualVol: 0, sharpe: 0, mdd: 0, winRate: 0 };

  const finalNav = nav[n - 1].nav;
  const totalReturn = finalNav - 1;

  // 年化收益（假设每季度 ≈ 0.25 年）
  const numQuarters = quarterlyReturns.length;
  const years = numQuarters / 4 || 0.25;
  const annualReturn = Math.pow(finalNav, 1 / years) - 1;

  // 年化波动率（季度收益标准差 × √4）
  const qRets = quarterlyReturns.map(q => q.return);
  let qMean = 0;
  for (const r of qRets) qMean += r;
  qMean /= qRets.length || 1;
  let qVar = 0;
  for (const r of qRets) qVar += (r - qMean) ** 2;
  qVar /= qRets.length || 1;
  const annualVol = Math.sqrt(qVar) * 2; // ×√4

  // 夏普比率（无风险利率 2%）
  const sharpe = annualVol > 0 ? (annualReturn - 0.02) / annualVol : 0;

  // 最大回撤
  let peak = 1, mdd = 0;
  for (const p of nav) {
    if (p.nav > peak) peak = p.nav;
    const dd = (p.nav - peak) / peak;
    if (dd < mdd) mdd = dd;
  }

  // 胜率
  const wins = qRets.filter(r => r > 0).length;
  const winRate = qRets.length > 0 ? wins / qRets.length : 0;

  // 基准指标
  let benchMetrics = null;
  if (benchmarkNav && benchmarkNav.length > 1) {
    const bFinal = benchmarkNav[benchmarkNav.length - 1].nav;
    const bTotal = bFinal - 1;
    const bAnnual = Math.pow(bFinal, 1 / years) - 1;
    benchMetrics = { totalReturn: bTotal, annualReturn: bAnnual };
  }

  return {
    totalReturn: totalReturn * 100,
    annualReturn: annualReturn * 100,
    annualVol: annualVol * 100,
    sharpe: sharpe,
    mdd: mdd * 100,
    winRate: winRate * 100,
    benchmark: benchMetrics
  };
}

/* ---------- 回归评估指标 ---------- */

function computeRegressionMetrics(yTrue, yPred) {
  const n = yTrue.length;
  if (n === 0) return { r2: 0, mse: 0, mae: 0, dirAcc: 0 };

  const yMean = yTrue.reduce((a, b) => a + b, 0) / n;
  let ssRes = 0, ssTot = 0, mse = 0, mae = 0, dirCorrect = 0;
  for (let i = 0; i < n; i++) {
    ssRes += (yTrue[i] - yPred[i]) ** 2;
    ssTot += (yTrue[i] - yMean) ** 2;
    mse += (yTrue[i] - yPred[i]) ** 2;
    mae += Math.abs(yTrue[i] - yPred[i]);
    if ((yTrue[i] > 0) === (yPred[i] > 0)) dirCorrect++;
  }
  return {
    r2: ssTot > 0 ? 1 - ssRes / ssTot : 0,
    mse: mse / n,
    mae: mae / n,
    dirAcc: (dirCorrect / n) * 100
  };
}

/* ---------- 导出 ---------- */

const RegEngine = {
  // 基础
  mulberry32, shuffle, shuffleIdx, identityMap, euclid,
  // 矩阵
  transpose, matMul, matVec, matrixInverse,
  // 因子
  FACTOR_DEFS, computeFactors,
  // 切分+标准化
  timeSplit, fitStandardize, fitMinMax,
  // 模型
  trainRidge, buildRegressionTree, trainRegressionForest, trainKNNRegressor,
  MODEL_REGISTRY,
  // 回测
  quarterlyBacktest, computeBacktestMetrics, computeRegressionMetrics,
};

if (typeof window !== "undefined") {
  window.RegEngine = RegEngine;
}
if (typeof module !== "undefined" && module.exports) {
  module.exports = RegEngine;
}
