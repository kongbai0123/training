import {
  buildSparklinePoints,
  extractMetricSeries,
  formatSequenceDate,
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
  const taskType = String(metrics?.task_type || summary.task_type || "").toLowerCase();
  const metricSchema = resolveRnnMetricSchema(metrics, summary);
  const bestMetrics = metrics?.best_metrics || summary.best_metrics || {};
  const history = Array.isArray(metrics?.history) ? metrics.history : [];
  const latestMetrics = history.length ? history[history.length - 1] : {};
  const metricSource = { ...latestMetrics, ...bestMetrics };
  const isRegression = taskType.includes("regression") ||
    metricSource["val/mae"] !== undefined || metricSource["val/rmse"] !== undefined;
  const primaryConfig = metricSchema.primary_metric || {};
  const qualityKeys = metricSchema.groups?.quality || [];
  const primary = isRegression
    ? { label: primaryConfig.display_name || "MAE", value: metricSource[primaryConfig.key || "val/mae"] ?? summary.primary_metric_value }
    : { label: primaryConfig.display_name || "Macro-F1", value: metricSource[primaryConfig.key || "val/macro_f1"] ?? summary.primary_metric_value };
  const secondary = isRegression
    ? { label: "RMSE", value: metricSource["val/rmse"] }
    : { label: qualityKeys.includes("val/accuracy") ? "Accuracy" : "Precision", value: metricSource[qualityKeys.includes("val/accuracy") ? "val/accuracy" : "val/precision"] ?? summary.best_accuracy };

  return {
    activeRun,
    summary,
    taskType,
    metricSchema,
    bestMetrics,
    history,
    latestMetrics,
    metricSource,
    isRegression,
    primary,
    secondary
  };
}

export function resolveRnnMetricSchema(metrics = {}, summary = {}) {
  const taskType = String(metrics?.task_type || summary?.task_type || "sequence_classification").toLowerCase();
  const suppliedSchema = metrics?.metric_schema || summary?.metric_schema;
  if (suppliedSchema?.primary_metric?.key && suppliedSchema?.groups) return suppliedSchema;
  const isRegression = taskType.includes("regression") || metrics?.best_metrics?.["val/mae"] !== undefined;
  if (isRegression) {
    return {
      primary_metric: { key: "val/mae", display_name: "MAE", goal: "minimize" },
      groups: { loss: ["train/loss", "val/loss"], quality: ["val/mae", "val/rmse"] }
    };
  }
  return {
    primary_metric: { key: "val/macro_f1", display_name: "Macro-F1", goal: "maximize" },
    groups: { loss: ["train/loss", "val/loss"], quality: ["val/accuracy", "val/macro_f1", "val/precision", "val/recall"] }
  };
}

export function buildRnnTaskAwareDashboard({ metrics = null, summary = {}, history = [], runs = [], metricsByRun = {}, comparisonMetric = "macro_f1" } = {}) {
  const metricSchema = resolveRnnMetricSchema(metrics, summary);
  const taskType = String(metrics?.task_type || summary?.task_type || "sequence_classification").toLowerCase();
  const isRegression = taskType.includes("regression") || metricSchema.primary_metric?.goal === "minimize";
  const qualityKeys = (metricSchema.groups?.quality || []).filter((key) => extractMetricSeries(history, key).length);
  const lossKeys = (metricSchema.groups?.loss || ["train/loss", "val/loss"]).filter((key) => extractMetricSeries(history, key).length);
  const labels = Array.isArray(history) ? history.map((row, index) => row.epoch ?? index + 1) : [];
  const latest = history?.length ? history[history.length - 1] : {};
  return {
    taskType,
    mode: isRegression ? "regression" : "classification",
    metricSchema,
    primaryMetric: metricSchema.primary_metric || {},
    chartCount: qualityKeys.length + lossKeys.length,
    scoreChart: {
      title: isRegression ? "Regression Error Curve" : "Classification Score Curve",
      note: `Schema quality: ${qualityKeys.length ? qualityKeys.join(", ") : "none"}`,
      labels,
      series: qualityKeys.map((key) => ({ key, label: metricLabel(key), values: extractMetricSeries(history, key) }))
    },
    lossChart: {
      title: "Loss Curve",
      note: `Schema loss: ${lossKeys.length ? lossKeys.join(", ") : "none"}`,
      labels,
      series: lossKeys.map((key) => ({ key, label: metricLabel(key), values: extractMetricSeries(history, key) }))
    },
    comparison: buildRnnBaselineComparisonViewModel({ runs, metricsByRun, metricKey: comparisonMetric }),
    diagnostic: buildRnnTaskDiagnostic({ metrics, latest, isRegression })
  };
}

function metricLabel(key = "") {
  const labels = {
    "val/accuracy": "Accuracy",
    "val/macro_f1": "Macro-F1",
    "val/precision": "Precision",
    "val/recall": "Recall",
    "val/mae": "MAE",
    "val/rmse": "RMSE",
    "train/loss": "Train Loss",
    "val/loss": "Val Loss"
  };
  return labels[key] || key;
}

function buildRnnTaskDiagnostic({ metrics = null, latest = {}, isRegression = false } = {}) {
  const confusion = metrics?.confusion_matrix || metrics?.confusionMatrix || null;
  const residuals = metrics?.residuals || metrics?.residual_samples || null;
  const predictionActual = metrics?.prediction_actual_samples || metrics?.predictionActualSamples || [];
  if (isRegression) {
    return {
      type: "residual",
      title: "Residual Diagnostic",
      badge: residuals?.length ? "residuals" : "schema-ready",
      residuals: Array.isArray(residuals) ? residuals.slice(0, 24).map((value) => Number(value)).filter(Number.isFinite) : [],
      predictionActual: Array.isArray(predictionActual) ? predictionActual.slice(0, 12) : [],
      cards: [
        ["MAE", formatSequenceMetric(latest["val/mae"])],
        ["RMSE", formatSequenceMetric(latest["val/rmse"])],
        ["Residual source", residuals?.length ? "Loaded from metrics payload" : "Raw prediction residuals are not persisted yet."]
      ]
    };
  }
  return {
    type: "confusion",
    title: "Confusion Matrix Diagnostic",
    badge: confusion?.length ? "matrix" : "schema-ready",
    matrix: Array.isArray(confusion) ? confusion : [],
    labels: metrics?.confusion_labels || metrics?.confusionLabels || [],
    cards: [
      ["Accuracy", formatSequenceMetric(latest["val/accuracy"])],
      ["Precision / Recall", `${formatSequenceMetric(latest["val/precision"])} / ${formatSequenceMetric(latest["val/recall"])}`],
      ["Matrix source", confusion?.length ? "Loaded from metrics payload" : "Confusion matrix is schema-ready; raw class counts are not persisted yet."]
    ]
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
      const latest = values.length ? values[values.length - 1] : null;
      return {
        ...chart,
        values,
        latest,
        latestPrefix: isSinglePointBaseline ? "Single-point baseline" : "Latest",
        latestLabel: formatSequenceMetric(latest),
        points: buildSparklinePoints(values),
        empty: values.length < 1,
        emptyMessage: "Not enough data"
      };
    })
  };
}

export function buildRnnEvaluationEpochRows(history = []) {
  if (!Array.isArray(history) || !history.length) {
    return {
      hasRows: false,
      emptyMessage: "No metric rows.",
      rows: []
    };
  }

  return {
    hasRows: true,
    emptyMessage: "",
    rows: history.map((row, index) => {
      const accuracyOrMae = row["val/accuracy"] ?? row["val/mae"];
      const macroOrRmse = row["val/macro_f1"] ?? row["val/rmse"];
      return {
        epoch: row.epoch ?? index + 1,
        trainLoss: formatSequenceMetric(row["train/loss"]),
        valLoss: formatSequenceMetric(row["val/loss"]),
        primary: formatSequenceMetric(accuracyOrMae),
        secondary: formatSequenceMetric(macroOrRmse),
        statusLabel: "Completed",
        statusClass: "badge-success"
      };
    })
  };
}

export function buildRnnEvaluationRunHistoryRows(runs = []) {
  if (!Array.isArray(runs) || !runs.length) {
    return {
      hasRows: false,
      emptyMessage: "No sequence runs.",
      rows: []
    };
  }

  return {
    hasRows: true,
    emptyMessage: "",
    rows: runs.map((run) => {
      const isRegression = String(run.task_type || "").includes("regression");
      const bestMetrics = run.best_metrics || {};
      const primaryLabel = run.primary_metric_name || (isRegression ? "MAE" : "Macro-F1");
      const primaryValue = run.primary_metric_value
        ?? (isRegression ? bestMetrics["val/mae"] ?? run.best_mae : bestMetrics["val/macro_f1"] ?? run.best_macro_f1)
        ?? run.platform_score;
      return {
        runId: run.run_id || "--",
        model: run.model || "--",
        backend: sequenceBackendDisplayLabel(run),
        primary: `${primaryLabel} ${formatSequenceMetric(primaryValue)}`,
        status: run.status || "--",
        statusClass: run.status === "completed" ? "badge-success" : "badge-warning",
        date: formatSequenceDate(run.completed_at || run.created_at || run.started_at)
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

  const rows = Array.from(grouped.values()).sort((a, b) => {
    if (metricConfig.lowerBetter) return a.value - b.value;
    return b.value - a.value;
  });
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

export function buildRnnBaselineComparisonViewModel({ runs = [], metricsByRun = {}, metricKey = "macro_f1" } = {}) {
  const comparison = buildRnnBaselineComparisonRows({ runs, metricsByRun, metricKey });
  let emptyMessage = "";
  if (!comparison.hasCompletedRuns) {
    emptyMessage = "No comparable runs loaded.";
  } else if (!comparison.hasAvailableRows) {
    emptyMessage = `No ${comparison.metricConfig.label} values loaded for completed runs.`;
  }

  return {
    metricKey,
    ...comparison,
    emptyMessage,
    rows: comparison.rows.map((row) => ({
      ...row,
      percentLabel: `${row.percent.toFixed(1)}%`,
      valueLabel: row.hasValue ? formatSequenceMetric(row.value) : "--"
    }))
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

export function buildRnnEvaluationSidebarViewModel(options = {}) {
  const sections = buildRnnEvaluationSidebarSections(options);
  return {
    statusSelector: "#rnn-eval-sidebar-status",
    status: sections.status,
    artifactRunId: options.activeRun?.run_id || "",
    rowSections: [
      { selector: "#rnn-eval-sidebar-run", rows: sections.runRows },
      { selector: "#rnn-eval-sidebar-dataset", rows: sections.datasetRows },
      { selector: "#rnn-eval-sidebar-metrics", rows: sections.metricRows }
    ]
  };
}
