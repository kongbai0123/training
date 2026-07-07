import { escapeHtml } from "../utils.js";
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
