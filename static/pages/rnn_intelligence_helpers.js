import { t } from "../state.js";

const CLASSIFICATION_KEYS = ["val/accuracy", "val/macro_f1", "val/precision", "val/recall"];
const REGRESSION_KEYS = ["val/mae", "val/rmse"];
const LOSS_KEYS = ["train/loss", "val/loss"];

function finite(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function metricSeries(history, key) {
  return (Array.isArray(history) ? history : []).map((row) => finite(row?.[key]));
}

function lastFinite(history, key) {
  const values = metricSeries(history, key).filter((value) => value !== null);
  return values.length ? values[values.length - 1] : null;
}

export function buildRnnLiveMonitorViewModel(trainState = {}) {
  const history = Array.isArray(trainState.metrics) ? trainState.metrics : [];
  const taskType = String(trainState.task_type || "").toLowerCase();
  const isRegression = taskType.includes("regression") || history.some((row) => row?.["val/mae"] !== undefined);
  const qualityKeys = (isRegression ? REGRESSION_KEYS : CLASSIFICATION_KEYS)
    .filter((key) => history.some((row) => finite(row?.[key]) !== null));
  const lossKeys = LOSS_KEYS.filter((key) => history.some((row) => finite(row?.[key]) !== null));
  const epoch = Number(trainState.epoch || 0);
  const totalEpochs = Number(trainState.total_epochs || 0);
  const progress = trainState.status === "completed"
    ? 100
    : totalEpochs > 0 ? Math.min(100, Math.max(0, (epoch / totalEpochs) * 100)) : 0;
  const latest = history.length ? history[history.length - 1] : {};
  const metricKeys = isRegression
    ? ["val/mae", "val/rmse", "train/loss", "val/loss"]
    : ["val/accuracy", "val/macro_f1", "val/precision", "val/recall"];
  return {
    visible: String(trainState.architecture || "").toLowerCase() === "rnn",
    status: String(trainState.status || "idle"),
    epoch,
    totalEpochs,
    progress,
    isRegression,
    cards: metricKeys.map((key) => ({ key, label: rnnMetricLabel(key), value: finite(latest?.[key]) })),
    qualityChart: buildLineChartModel(history, qualityKeys),
    lossChart: buildLineChartModel(history, lossKeys)
  };
}

function buildLineChartModel(history, keys) {
  return {
    labels: (Array.isArray(history) ? history : []).map((row, index) => row?.epoch ?? index + 1),
    series: keys.map((key) => ({ key, label: rnnMetricLabel(key), values: metricSeries(history, key) }))
  };
}

export function buildRnnSmartAssessment({ metrics = {}, summary = {}, config = {} } = {}) {
  const history = Array.isArray(metrics.history) ? metrics.history : [];
  const mergedConfig = { ...(config || {}), ...(metrics.train_config || {}) };
  const taskType = String(metrics.task_type || summary.task_type || "sequence_classification").toLowerCase();
  const isRegression = taskType.includes("regression") || lastFinite(history, "val/mae") !== null;
  const best = metrics.best_metrics || summary.best_metrics || {};
  const latest = history.length ? history[history.length - 1] : best;
  const bestEpoch = Number(metrics.best_epoch || summary.best_epoch || 0);
  const totalEpochs = Number(metrics.total_epochs || mergedConfig.epochs || history.length || 0);
  const signals = [];
  let score = 70;

  if (isRegression) {
    const mae = finite(best["val/mae"] ?? latest["val/mae"]);
    const rmse = finite(best["val/rmse"] ?? latest["val/rmse"]);
    if (mae !== null && rmse !== null && mae > 0) {
      const ratio = rmse / mae;
      if (ratio >= 1.8) {
        signals.push({ code: "regression_outliers", tone: "warning", values: { ratio: ratio.toFixed(2) } });
        score -= 14;
      } else {
        signals.push({ code: "regression_stable", tone: "success", values: { ratio: ratio.toFixed(2) } });
        score += 8;
      }
    }
  } else {
    const f1 = finite(best["val/macro_f1"] ?? latest["val/macro_f1"]);
    const accuracy = finite(best["val/accuracy"] ?? latest["val/accuracy"]);
    const precision = finite(best["val/precision"] ?? latest["val/precision"]);
    const recall = finite(best["val/recall"] ?? latest["val/recall"]);
    const quality = [f1, accuracy].filter((value) => value !== null);
    if (quality.length) score = Math.round(quality.reduce((sum, value) => sum + value, 0) / quality.length * 100);
    if (f1 !== null && f1 < 0.6) signals.push({ code: "low_macro_f1", tone: "danger", values: { value: f1.toFixed(3) } });
    else if (f1 !== null && f1 < 0.8) signals.push({ code: "moderate_macro_f1", tone: "warning", values: { value: f1.toFixed(3) } });
    else if (f1 !== null) signals.push({ code: "strong_macro_f1", tone: "success", values: { value: f1.toFixed(3) } });
    if (precision !== null && recall !== null && Math.abs(precision - recall) >= 0.12) {
      signals.push({
        code: precision > recall ? "recall_gap" : "precision_gap",
        tone: "warning",
        values: { precision: precision.toFixed(3), recall: recall.toFixed(3) }
      });
      score -= 8;
    }
  }

  const trainLoss = finite(latest["train/loss"]);
  const valLoss = finite(latest["val/loss"]);
  if (trainLoss !== null && valLoss !== null && trainLoss > 0 && valLoss / trainLoss >= 1.5) {
    signals.push({ code: "overfit_gap", tone: "warning", values: { ratio: (valLoss / trainLoss).toFixed(2) } });
    score -= 12;
  }
  if (bestEpoch > 0 && totalEpochs >= 5 && bestEpoch <= Math.max(2, Math.floor(totalEpochs * 0.35))) {
    signals.push({ code: "early_peak", tone: "warning", values: { best: bestEpoch, total: totalEpochs } });
    score -= 6;
  } else if (bestEpoch > 0 && totalEpochs > 0 && bestEpoch >= Math.ceil(totalEpochs * 0.85)) {
    signals.push({ code: "late_peak", tone: "info", values: { best: bestEpoch, total: totalEpochs } });
  }
  const stoppedReason = String(metrics.stopped_reason || summary.termination_reason || "");
  if (stoppedReason === "early_stopping") {
    signals.push({ code: "early_stopping", tone: "info", values: { best: bestEpoch } });
  }
  if (!signals.length) signals.push({ code: "insufficient_context", tone: "info", values: {} });

  score = Math.max(0, Math.min(100, Math.round(score)));
  const verdict = score >= 85 ? "strong" : score >= 70 ? "usable" : score >= 50 ? "attention" : "weak";
  const dataset = metrics.dataset_summary || {};
  return {
    score,
    verdict,
    isRegression,
    signals: signals.slice(0, 6),
    context: [
      [t("rnn.intelligence.context.model"), mergedConfig.model || summary.model || summary.backend || "--"],
      [t("rnn.intelligence.context.task"), isRegression ? t("rnn.task.regression") : t("rnn.task.classification")],
      [t("rnn.intelligence.context.epochs"), `${history.length || bestEpoch || 0} / ${totalEpochs || "--"}`],
      [t("rnn.intelligence.context.bestEpoch"), bestEpoch || "--"],
      [t("rnn.intelligence.context.sequenceLength"), mergedConfig.sequence_length || dataset.sequence_length || "--"],
      [t("rnn.intelligence.context.samples"), dataset.window_count || dataset.sample_count || dataset.sequence_count || "--"]
    ]
  };
}

export function rnnMetricLabel(key = "") {
  const labels = {
    "val/accuracy": "Accuracy",
    "val/macro_f1": "Macro-F1",
    "val/precision": "Precision",
    "val/recall": "Recall",
    "val/mae": "MAE",
    "val/rmse": "RMSE",
    "train/loss": t("rnn.evaluation.trainLoss"),
    "val/loss": t("rnn.evaluation.valLoss")
  };
  return labels[key] || key;
}

function xml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;" }[char]));
}

export function buildRnnLineChartSvg({ title = "RNN metrics", labels = [], series = [] } = {}) {
  const width = 1200;
  const height = 620;
  const plot = { left: 90, top: 90, width: 1060, height: 440 };
  const palette = ["#2563eb", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444"];
  const values = series.flatMap((item) => (item.values || []).filter((value) => finite(value) !== null).map(Number));
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 1;
  const spread = Math.max(max - min, 0.000001);
  const x = (index) => plot.left + (labels.length <= 1 ? plot.width / 2 : index / (labels.length - 1) * plot.width);
  const y = (value) => plot.top + plot.height - ((Number(value) - min) / spread * plot.height);
  const grid = Array.from({ length: 6 }, (_, index) => {
    const gy = plot.top + index / 5 * plot.height;
    const value = max - index / 5 * spread;
    return `<line x1="${plot.left}" y1="${gy}" x2="${plot.left + plot.width}" y2="${gy}" stroke="#dbe3ef"/><text x="${plot.left - 14}" y="${gy + 5}" text-anchor="end" fill="#475569" font-size="14">${xml(value.toFixed(4))}</text>`;
  }).join("");
  const lines = series.map((item, seriesIndex) => {
    const points = (item.values || []).map((value, index) => finite(value) === null ? null : `${x(index).toFixed(1)},${y(value).toFixed(1)}`).filter(Boolean).join(" ");
    return `<polyline points="${points}" fill="none" stroke="${palette[seriesIndex % palette.length]}" stroke-width="3" stroke-linejoin="round"/>`;
  }).join("");
  const legend = series.map((item, index) => `<g transform="translate(${plot.left + index * 220},48)"><line x1="0" y1="0" x2="28" y2="0" stroke="${palette[index % palette.length]}" stroke-width="4"/><text x="38" y="5" fill="#1e293b" font-size="16">${xml(item.label || item.key)}</text></g>`).join("");
  const xLabels = labels.length ? [0, Math.floor((labels.length - 1) / 2), labels.length - 1].filter((value, index, all) => all.indexOf(value) === index).map((index) => `<text x="${x(index)}" y="${plot.top + plot.height + 34}" text-anchor="middle" fill="#475569" font-size="14">${xml(labels[index])}</text>`).join("") : "";
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect width="100%" height="100%" fill="#ffffff"/><text x="${plot.left}" y="30" fill="#0f172a" font-size="22" font-family="Arial, sans-serif" font-weight="700">${xml(title)}</text>${legend}${grid}<line x1="${plot.left}" y1="${plot.top + plot.height}" x2="${plot.left + plot.width}" y2="${plot.top + plot.height}" stroke="#64748b"/>${lines}${xLabels}<text x="620" y="600" text-anchor="middle" fill="#475569" font-size="15">Epoch</text></svg>`;
}

export function buildRnnBarChartSvg({ title = "Run comparison", rows = [] } = {}) {
  const width = 1000;
  const height = 560;
  const max = Math.max(...rows.map((row) => Math.abs(Number(row.value) || 0)), 0.000001);
  const barWidth = Math.max(30, Math.min(120, 760 / Math.max(rows.length, 1) - 24));
  const bars = rows.map((row, index) => {
    const x = 120 + index * (760 / Math.max(rows.length, 1)) + 12;
    const barHeight = Math.abs(Number(row.value) || 0) / max * 340;
    const y = 430 - barHeight;
    return `<rect x="${x}" y="${y}" width="${barWidth}" height="${barHeight}" rx="5" fill="#2563eb"/><text x="${x + barWidth / 2}" y="${y - 10}" text-anchor="middle" fill="#1e293b" font-size="14">${xml(Number(row.value).toFixed(4))}</text><text x="${x + barWidth / 2}" y="458" text-anchor="middle" fill="#475569" font-size="13">${xml(row.label)}</text>`;
  }).join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect width="100%" height="100%" fill="#fff"/><text x="60" y="45" fill="#0f172a" font-size="22" font-family="Arial, sans-serif" font-weight="700">${xml(title)}</text><line x1="90" y1="430" x2="930" y2="430" stroke="#64748b"/>${bars}</svg>`;
}

export function buildRnnDiagnosticSvg(diagnostic = {}) {
  const width = 900;
  const height = 650;
  const title = diagnostic.title || "RNN diagnostic";
  if (diagnostic.type === "confusion" && Array.isArray(diagnostic.matrix) && diagnostic.matrix.length) {
    const matrix = diagnostic.matrix;
    const size = Math.min(480 / matrix.length, 90);
    const max = Math.max(...matrix.flat().map(Number), 1);
    const cells = matrix.flatMap((row, r) => row.map((value, c) => {
      const opacity = 0.12 + Number(value) / max * 0.78;
      return `<rect x="${180 + c * size}" y="${100 + r * size}" width="${size}" height="${size}" fill="#2563eb" fill-opacity="${opacity}" stroke="#fff"/><text x="${180 + c * size + size / 2}" y="${100 + r * size + size / 2 + 5}" text-anchor="middle" fill="#0f172a" font-size="14">${xml(value)}</text>`;
    })).join("");
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect width="100%" height="100%" fill="#fff"/><text x="50" y="45" fill="#0f172a" font-size="22" font-family="Arial" font-weight="700">${xml(title)}</text><text x="50" y="330" transform="rotate(-90 50 330)" text-anchor="middle" fill="#475569">Actual</text>${cells}<text x="420" y="620" text-anchor="middle" fill="#475569">Prediction</text></svg>`;
  }
  const residuals = Array.isArray(diagnostic.residuals) ? diagnostic.residuals.map(Number).filter(Number.isFinite) : [];
  const max = Math.max(...residuals.map(Math.abs), 0.000001);
  const barWidth = Math.max(2, 760 / Math.max(residuals.length, 1));
  const bars = residuals.map((value, index) => {
    const magnitude = Math.abs(value) / max * 220;
    const y = value >= 0 ? 310 - magnitude : 310;
    return `<rect x="${90 + index * barWidth}" y="${y}" width="${Math.max(1, barWidth - 1)}" height="${magnitude}" fill="${value >= 0 ? "#10b981" : "#ef4444"}"/>`;
  }).join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect width="100%" height="100%" fill="#fff"/><text x="50" y="45" fill="#0f172a" font-size="22" font-family="Arial" font-weight="700">${xml(title)}</text><line x1="80" y1="310" x2="870" y2="310" stroke="#64748b"/>${bars}<text x="450" y="600" text-anchor="middle" fill="#475569">Sample</text></svg>`;
}
