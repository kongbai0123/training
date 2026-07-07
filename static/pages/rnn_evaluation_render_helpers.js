import { escapeHtml } from "../utils.js";

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
