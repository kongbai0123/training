import {
  buildSparklinePoints,
  extractMetricSeries,
  formatSequenceMetric,
  normalizeRnnModelGroupLabel,
  resolveComparisonMetricConfig,
  resolveRunComparisonMetric,
  sequenceBackendDisplayLabel
} from "./rnn_metric_helpers.js";

export function isSequenceEvaluationRun(run) {
  const architecture = String(run?.architecture || "").toLowerCase();
  const backend = String(run?.backend || "").toLowerCase();
  const taskType = String(run?.task_type || run?.task || "").toLowerCase();
  const model = String(run?.model || "").toLowerCase();
  return (
    architecture === "rnn" ||
    backend === "pytorch_lstm" ||
    backend === "sklearn_xgboost" ||
    taskType.includes("sequence") ||
    model.includes("xgboost")
  );
}

export function resolveRnnEvaluationViewModel({ runs = [], metrics = null, selectedRunId = "" } = {}) {
  const safeRuns = Array.isArray(runs) ? runs : [];
  const activeRun = safeRuns.find((run) => run.run_id === selectedRunId) || safeRuns[0] || null;
  const summary = activeRun || {};
  const bestMetrics = metrics?.best_metrics || summary.best_metrics || {};
  const history = Array.isArray(metrics?.history) ? metrics.history : [];
  const latestMetrics = history.length ? history[history.length - 1] : {};
  const metricSource = { ...latestMetrics, ...bestMetrics };
  const isRegression = String(metrics?.task_type || summary.task_type || "").toLowerCase().includes("regression") ||
    metricSource["val/mae"] !== undefined || metricSource["val/rmse"] !== undefined;
  const primary = isRegression
    ? { label: "MAE", value: metricSource["val/mae"] ?? summary.primary_metric_value }
    : { label: "Accuracy", value: metricSource["val/accuracy"] ?? summary.best_accuracy };
  const secondary = isRegression
    ? { label: "RMSE", value: metricSource["val/rmse"] }
    : { label: "Macro-F1", value: metricSource["val/macro_f1"] ?? summary.primary_metric_value };

  return {
    activeRun,
    summary,
    bestMetrics,
    history,
    latestMetrics,
    metricSource,
    isRegression,
    primary,
    secondary
  };
}

export function isSinglePointBaselineRun(context = {}, history = []) {
  const backend = String(context.backend || "").toLowerCase();
  const model = String(context.model || "").toLowerCase();
  if (!(backend === "sklearn_xgboost" || model.includes("xgboost"))) return false;
  const metricKeys = ["val/accuracy", "val/macro_f1", "val/mae", "val/rmse"];
  return metricKeys.some((key) => extractMetricSeries(history, key).length <= 1);
}

export function buildRnnMetricTrendRows({ history = [], isRegression = false, metricContext = {} } = {}) {
  const safeHistory = Array.isArray(history) ? history : [];
  const isSinglePointBaseline = isSinglePointBaselineRun(metricContext, safeHistory);
  if (!safeHistory.length) {
    return {
      isSinglePointBaseline,
      hasHistory: false,
      emptyMessage: "No metric trend loaded.",
      charts: []
    };
  }

  const chartDefinitions = isRegression
    ? [
      { label: "MAE", key: "val/mae" },
      { label: "RMSE", key: "val/rmse" },
      { label: "Train Loss", key: "train/loss" },
      { label: "Val Loss", key: "val/loss" }
    ]
    : [
      { label: "Accuracy", key: "val/accuracy" },
      { label: "Macro-F1", key: "val/macro_f1" },
      { label: "Train Loss", key: "train/loss" },
      { label: "Val Loss", key: "val/loss" }
    ];

  return {
    isSinglePointBaseline,
    hasHistory: true,
    emptyMessage: "",
    charts: chartDefinitions.map((chart) => {
      const values = extractMetricSeries(safeHistory, chart.key);
      return {
        ...chart,
        values,
        latest: values.length ? values[values.length - 1] : null,
        points: buildSparklinePoints(values),
        empty: values.length < 1
      };
    })
  };
}

export function buildRnnBaselineComparisonRows({ runs = [], metricsByRun = {}, metricKey = "macro_f1" } = {}) {
  const metricConfig = resolveComparisonMetricConfig(metricKey);
  const completedRuns = (Array.isArray(runs) ? runs : []).filter((run) => String(run.status || "").toLowerCase() === "completed");
  const grouped = new Map();
  completedRuns.forEach((run) => {
    const key = normalizeRnnModelGroupLabel(run);
    const metrics = metricsByRun[run.run_id] || {};
    const value = resolveRunComparisonMetric(run, metrics, metricConfig);
    if (!Number.isFinite(value)) return;
    const current = grouped.get(key);
    const better = !current || (metricConfig.lowerBetter ? value < current.value : value > current.value);
    if (better) grouped.set(key, { label: key, value, run, metricConfig });
  });

  const order = ["LSTM", "GRU", "BiLSTM", "XGBoost"];
  const rows = order.map((label) => grouped.get(label) || { label, value: null, metricConfig });
  const availableRows = rows.filter((row) => Number.isFinite(row.value));
  const values = availableRows.map((row) => row.value);
  const max = Math.max(...values, 0.000001);
  const min = values.length ? Math.min(...values) : 0;
  return {
    metricConfig,
    hasCompletedRuns: completedRuns.length > 0,
    hasAvailableRows: availableRows.length > 0,
    rows: rows.map((row) => {
      const hasValue = Number.isFinite(row.value);
      const percent = !hasValue
        ? 0
        : metricConfig.lowerBetter
          ? Math.max(4, ((max - row.value) / Math.max(max - min, 0.000001)) * 100)
          : Math.max(4, (row.value / max) * 100);
      return { ...row, hasValue, percent };
    })
  };
}

export function buildRnnEvaluationSidebarSections({
  activeRun = null,
  metrics = null,
  readiness = {},
  config = {},
  metricSource = {},
  isRegression = false,
  primary = { label: "Accuracy", value: null },
  secondary = { label: "Macro-F1", value: null }
} = {}) {
  const dataset = metrics?.dataset_summary || {};
  const splitCounts = dataset.split_counts || readiness.split_counts || {};
  const splitText = ["train", "val", "test"].map((key) => `${key}: ${splitCounts[key] ?? 0}`).join(" / ");
  const modelLabel = activeRun?.model || metrics?.model || sequenceBackendDisplayLabel(activeRun || metrics || {});
  const backendLabel = metrics?.backend || activeRun?.backend || "--";
  const taskLabel = isRegression ? "regression" : "classification";

  return {
    status: {
      className: `summary-badge ${activeRun ? "badge-success" : "badge-neutral"}`,
      text: activeRun ? activeRun.status || "loaded" : "No run"
    },
    runRows: [
      ["Run ID", activeRun?.run_id || "--", true],
      ["Model", modelLabel || "--"],
      ["Backend", backendLabel || "--", true],
      ["Status", activeRun?.status || "--"],
      ["Task", activeRun?.task_type || metrics?.task_type || taskLabel]
    ],
    datasetRows: [
      ["CSV files", String((dataset.csv_files || []).length || readiness.csv_files || 0)],
      ["Sequences", String(dataset.sequence_count ?? readiness.sequence_count ?? "--")],
      ["Feature dim", String(dataset.feature_dim ?? readiness.feature_dim ?? "--")],
      ["Split", splitText],
      ["Window", `length ${dataset.sequence_length ?? config.sequence_length ?? "--"} / stride ${dataset.stride ?? config.stride ?? "--"} / horizon ${config.horizon ?? "--"}`]
    ],
    metricRows: [
      [primary.label, formatSequenceMetric(primary.value)],
      [secondary.label, formatSequenceMetric(secondary.value)],
      ["Val Loss", formatSequenceMetric(metricSource?.["val/loss"])],
      ["Best epoch", String(metrics?.best_epoch ?? activeRun?.best_epoch ?? "--")]
    ]
  };
}
