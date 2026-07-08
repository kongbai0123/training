import { escapeHtml } from "../utils.js";
import { t } from "../state.js";
import { formatSequenceMetric } from "./rnn_metric_helpers.js";

export function resolveRnnEvaluationRunBadge({ hasMetrics = false, loading = false, activeRun = null, backend = "" } = {}) {
  return {
    className: `summary-badge ${hasMetrics ? "badge-success" : loading ? "badge-neutral" : "badge-warning"}`,
    text: loading ? "Loading" : activeRun ? backend : "No run"
  };
}

export function resolveRnnEvaluationMessage({ loading = false, activeRun = null } = {}) {
  return {
    hidden: Boolean(activeRun && !loading),
    text: loading
      ? "Loading sequence training metrics, artifacts, and run history..."
      : activeRun
        ? ""
        : "No RNN or XGBoost training run found for this project."
  };
}

export function resolveRnnEvaluationOverviewRender({
  hasMetrics = false,
  loading = false,
  activeRun = null,
  backend = "",
  primary = {},
  secondary = {},
  metricSource = {}
} = {}) {
  return {
    badge: resolveRnnEvaluationRunBadge({ hasMetrics, loading, activeRun, backend }),
    message: resolveRnnEvaluationMessage({ loading, activeRun }),
    primaryLabel: primary.label,
    primaryValue: formatSequenceMetric(primary.value),
    secondaryLabel: secondary.label,
    secondaryValue: formatSequenceMetric(secondary.value),
    trainLoss: formatSequenceMetric(metricSource["train/loss"]),
    valLoss: formatSequenceMetric(metricSource["val/loss"])
  };
}

export function resolveRnnEvaluationSidebarStatusRender(sidebar = {}) {
  return {
    selector: sidebar.statusSelector,
    className: sidebar.status?.className || "summary-badge badge-neutral",
    text: sidebar.status?.text || "No run"
  };
}

export function renderRnnEvaluationEpochTableRows(epochRows = {}) {
  if (!epochRows.hasRows) {
    return `<tr><td colspan="6">${escapeHtml(epochRows.emptyMessage)}</td></tr>`;
  }

  return (epochRows.rows || []).map((row) => {
    return `<tr>
      <td><strong>${escapeHtml(row.epoch)}</strong></td>
      <td><code>${escapeHtml(row.trainLoss)}</code></td>
      <td><code>${escapeHtml(row.valLoss)}</code></td>
      <td>${escapeHtml(row.primary)}</td>
      <td>${escapeHtml(row.secondary)}</td>
      <td><span class="badge ${escapeHtml(row.statusClass)}">${escapeHtml(row.statusLabel)}</span></td>
    </tr>`;
  }).join("");
}

export function renderRnnEvaluationArtifactList(artifactList = {}) {
  if (!artifactList.hasArtifacts) return escapeHtml(artifactList.emptyMessage);

  return (artifactList.rows || []).map((artifact) => {
    return `<div class="rnn-result-item">
      <div>
        <strong>${escapeHtml(artifact.filename)}</strong>
        <span>${escapeHtml(artifact.relPath)} · ${escapeHtml(artifact.sizeLabel)}</span>
      </div>
      <a class="btn btn-secondary btn-sm" href="${escapeHtml(artifact.downloadUrl)}" target="_blank" download>Download</a>
    </div>`;
  }).join("");
}

export function renderRnnMetricTrendChartStack(trendRows = {}) {
  if (!trendRows.hasHistory) {
    return `<div class="rnn-eval-chart-empty">${escapeHtml(trendRows.emptyMessage)}</div>`;
  }

  return (trendRows.charts || []).map((chart) => {
    return `<div class="rnn-eval-chart-row">
      <div class="rnn-eval-chart-label">
        <strong>${escapeHtml(chart.label)}</strong>
        <span>${escapeHtml(chart.latestPrefix)} ${escapeHtml(chart.latestLabel)}</span>
      </div>
      <div class="rnn-eval-sparkline ${chart.empty ? "is-empty" : ""}">
        ${chart.empty
          ? `<span>${escapeHtml(chart.emptyMessage)}</span>`
          : `<svg viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden="true"><polyline points="${escapeHtml(chart.points)}"></polyline></svg>`}
      </div>
    </div>`;
  }).join("");
}

export function renderRnnEvaluationSidebarRows(rows = []) {
  return rows.map(([label, value, isCode]) => {
    const safeValue = escapeHtml(value ?? "--");
    const valueHtml = isCode ? `<code>${safeValue}</code>` : `<span>${safeValue}</span>`;
    return `<div class="summary-row"><span>${escapeHtml(label)}</span>${valueHtml}</div>`;
  }).join("");
}

export function renderRnnEvaluationRunHistoryTableRows(runRows = {}) {
  if (!runRows.hasRows) {
    return `<tr><td colspan="6">${escapeHtml(runRows.emptyMessage)}</td></tr>`;
  }

  return (runRows.rows || []).map((run) => {
    return `<tr>
      <td><code>${escapeHtml(run.runId)}</code></td>
      <td>${escapeHtml(run.model)}</td>
      <td>${escapeHtml(run.backend)}</td>
      <td>${escapeHtml(run.primary)}</td>
      <td><span class="badge ${escapeHtml(run.statusClass)}">${escapeHtml(run.status)}</span></td>
      <td>${escapeHtml(run.date)}</td>
    </tr>`;
  }).join("");
}

export function renderRnnBaselineComparisonChart(comparison = {}) {
  if (!comparison.hasCompletedRuns || !comparison.hasAvailableRows) {
    return `<div class="rnn-eval-chart-empty">${escapeHtml(comparison.emptyMessage)}</div>`;
  }

  return (comparison.rows || []).map((row) => {
    return `<div class="rnn-compare-mini-row ${row.hasValue ? "" : "is-missing"}">
      <div class="rnn-compare-mini-label">
        <strong>${escapeHtml(row.label)}</strong>
        <span>${escapeHtml(comparison.metricConfig?.hint)}</span>
      </div>
      <div class="rnn-compare-mini-track"><span style="width: ${escapeHtml(row.percentLabel)};"></span></div>
      <code>${escapeHtml(row.valueLabel)}</code>
    </div>`;
  }).join("");
}

export function renderRnnTaskDiagnostic(diagnostic = {}) {
  if (!diagnostic.type) {
    return `<div class="rnn-eval-chart-empty">${escapeHtml(t("rnn.evaluation.noTaskDiagnostic"))}</div>`;
  }
  const cards = (diagnostic.cards || []).map(([label, value]) => `
    <div class="rnn-diagnostic-card">
      <strong>${escapeHtml(label)}</strong>
      <span>${escapeHtml(value ?? "--")}</span>
    </div>
  `).join("");

  if (diagnostic.type === "residual") {
    const residuals = diagnostic.residuals || [];
    const max = Math.max(...residuals.map((value) => Math.abs(value)), 0.000001);
    const statsCards = (diagnostic.stats || []).map(([label, value]) => `
      <div class="rnn-diagnostic-stat">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value ?? "--")}</strong>
      </div>
    `).join("");
    const metadata = (diagnostic.summaryMeta || []).length
      ? `<div class="rnn-diagnostic-meta">${diagnostic.summaryMeta.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>`
      : "";
    const bars = residuals.length
      ? residuals.map((value) => {
          const height = Math.max(8, (Math.abs(value) / max) * 72);
          const directionClass = value < 0 ? "is-negative" : "is-positive";
          return `<span class="rnn-residual-bar ${directionClass}" title="${escapeHtml(formatSequenceMetric(value))}" style="height: ${escapeHtml(height.toFixed(1))}px"></span>`;
        }).join("")
      : `<div class="rnn-eval-chart-empty">${escapeHtml(t("rnn.evaluation.noResidualSamples"))}</div>`;
    const sampleRows = (diagnostic.predictionActual || []).length
      ? `<div class="rnn-result-table-wrap">
          <table class="rnn-result-table rnn-diagnostic-table">
            <thead><tr><th>#</th><th>${escapeHtml(t("rnn.inference.prediction"))}</th><th>${escapeHtml(t("rnn.evaluation.actual"))}</th><th>${escapeHtml(t("rnn.evaluation.residual"))}</th></tr></thead>
            <tbody>${diagnostic.predictionActual.map((row, index) => `
              <tr>
                <td>${index + 1}</td>
                <td><code>${escapeHtml(formatSequenceMetric(row.prediction))}</code></td>
                <td><code>${escapeHtml(formatSequenceMetric(row.actual))}</code></td>
                <td><code>${escapeHtml(formatSequenceMetric(row.residual))}</code></td>
              </tr>
            `).join("")}</tbody>
          </table>
        </div>`
      : `<div class="rnn-eval-chart-empty">${escapeHtml(t("rnn.evaluation.noPredictionActual"))}</div>`;
    const outlierRows = (diagnostic.outliers || []).length
      ? `<div class="rnn-result-table-wrap">
          <table class="rnn-result-table rnn-diagnostic-table">
            <thead><tr><th>${escapeHtml(t("rnn.evaluation.sample"))}</th><th>${escapeHtml(t("rnn.inference.prediction"))}</th><th>${escapeHtml(t("rnn.evaluation.actual"))}</th><th>${escapeHtml(t("rnn.evaluation.residual"))}</th><th>|Residual|</th></tr></thead>
            <tbody>${diagnostic.outliers.map((row) => `
              <tr>
                <td>${escapeHtml(row.sample)}</td>
                <td><code>${escapeHtml(formatSequenceMetric(row.prediction))}</code></td>
                <td><code>${escapeHtml(formatSequenceMetric(row.actual))}</code></td>
                <td><code>${escapeHtml(formatSequenceMetric(row.residual))}</code></td>
                <td><code>${escapeHtml(formatSequenceMetric(row.absResidual))}</code></td>
              </tr>
            `).join("")}</tbody>
          </table>
        </div>`
      : `<div class="rnn-eval-chart-empty">${escapeHtml(t("rnn.evaluation.noOutliers"))}</div>`;
    return `
      ${metadata}
      <div class="rnn-diagnostic-stats">${statsCards}</div>
      <div class="rnn-diagnostic-card rnn-diagnostic-wide">
        <div class="rnn-diagnostic-card-head">
          <strong>${escapeHtml(t("rnn.evaluation.residualPlot"))}</strong>
          <span>Magnitude and direction of sample errors</span>
        </div>
        <div class="rnn-residual-preview">${bars}</div>
      </div>
      <div class="rnn-diagnostic-card rnn-diagnostic-wide">
        <strong>${escapeHtml(t("rnn.evaluation.predictionActual"))}</strong>
        ${sampleRows}
      </div>
      <div class="rnn-diagnostic-card rnn-diagnostic-wide">
        <strong>${escapeHtml(t("rnn.evaluation.outliers"))}</strong>
        <p>${escapeHtml(t("rnn.evaluation.outliersHelp"))}</p>
        ${outlierRows}
      </div>
    `;
  }

  const matrix = diagnostic.matrix || [];
  const labels = diagnostic.labels || [];
  const gridStyle = matrix.length ? ` style="grid-template-columns: repeat(${Math.max(1, Math.min(matrix.length, 8))}, minmax(0, 1fr));"` : "";
  const cells = matrix.length
    ? matrix.flat().slice(0, 64).map((value, index) => {
        const row = Math.floor(index / matrix.length);
        const col = index % matrix.length;
        const title = t("rnn.evaluation.confusionCellTitle", {
          actual: labels[row] ?? row,
          prediction: labels[col] ?? col
        });
        return `<span class="rnn-confusion-cell" title="${escapeHtml(title)}">${escapeHtml(value)}</span>`;
      }).join("")
    : `
      <span class="rnn-confusion-cell">TP</span>
      <span class="rnn-confusion-cell">FP</span>
      <span class="rnn-confusion-cell">FN</span>
      <span class="rnn-confusion-cell">TN</span>
    `;
  return `
    <div class="rnn-diagnostic-grid">${cards}</div>
    <div class="rnn-diagnostic-card">
      <strong>Confusion Matrix</strong>
      <p>${escapeHtml(matrix.length ? "Loaded class-count matrix." : "Matrix placeholder shown until class-count data is persisted.")}</p>
      <div class="rnn-confusion-preview"${gridStyle}>${cells}</div>
    </div>
  `;
}
