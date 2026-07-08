export function resolveComparisonMetricConfig(metricKey) {
  const configs = {
    accuracy: { key: "val/accuracy", label: "Accuracy", hint: "higher better", lowerBetter: false, runFields: ["best_accuracy", "accuracy"] },
    macro_f1: { key: "val/macro_f1", label: "Macro-F1", hint: "higher better", lowerBetter: false, runFields: ["best_macro_f1", "macro_f1", "primary_metric_value"] },
    precision: { key: "val/precision", label: "Precision", hint: "higher better", lowerBetter: false, runFields: ["best_precision", "precision"] },
    recall: { key: "val/recall", label: "Recall", hint: "higher better", lowerBetter: false, runFields: ["best_recall", "recall"] },
    mae: { key: "val/mae", label: "MAE", hint: "lower better", lowerBetter: true, runFields: ["best_mae", "mae", "primary_metric_value"] },
    rmse: { key: "val/rmse", label: "RMSE", hint: "lower better", lowerBetter: true, runFields: ["best_rmse", "rmse"] },
    val_loss: { key: "val/loss", label: "Val Loss", hint: "lower better", lowerBetter: true, runFields: ["best_val_loss", "val_loss"] }
  };
  return configs[metricKey] || configs.macro_f1;
}

export function normalizeRnnModelGroupLabel(run = {}) {
  const model = String(run.model || "").toLowerCase();
  const runId = String(run.run_id || "").toLowerCase();
  const backend = String(run.backend || "").toLowerCase();
  const source = `${model} ${runId}`;
  if (source.includes("xgboost") || backend === "sklearn_xgboost") return "XGBoost";
  if (source.includes("bilstm") || run.bidirectional) return "BiLSTM";
  if (source.includes("gru")) return "GRU";
  return "LSTM";
}

export function resolveRunComparisonMetric(run = {}, metrics = {}, metricConfig = resolveComparisonMetricConfig("macro_f1")) {
  const bestMetrics = metrics.best_metrics || {};
  const history = Array.isArray(metrics.history) ? metrics.history : [];
  const historyValues = extractMetricSeries(history, metricConfig.key);
  if (historyValues.length) {
    return metricConfig.lowerBetter ? Math.min(...historyValues) : Math.max(...historyValues);
  }
  const direct = bestMetrics[metricConfig.key];
  if (direct !== undefined && direct !== null && direct !== "") return Number(direct);
  for (const field of metricConfig.runFields || []) {
    const value = run[field];
    if (value !== undefined && value !== null && value !== "") return Number(value);
  }
  return Number.NaN;
}

export function extractMetricSeries(history, key) {
  return history
    .map((row) => Number(row?.[key]))
    .filter((value) => Number.isFinite(value));
}

export function buildSparklinePoints(values) {
  if (!values.length) return "";
  if (values.length === 1) return "0.00,16.00 100.00,16.00";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = Math.max(max - min, 0.000001);
  return values.map((value, index) => {
    const x = values.length === 1 ? 50 : (index / (values.length - 1)) * 100;
    const y = 28 - ((value - min) / spread) * 24;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ");
}

export function sequenceBackendDisplayLabel(run = {}) {
  const backend = String(run.backend || "").toLowerCase();
  if (backend === "sklearn_xgboost") return "XGBoost";
  if (backend === "pytorch_lstm") return "LSTM / GRU";
  return run.backend || "Sequence";
}

export function formatSequenceMetric(value, digits = 3) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) return "--";
  return Number(value).toFixed(digits);
}

export function formatSequenceDate(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
