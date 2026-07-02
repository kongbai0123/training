import { appState, t } from "../state.js";
import { eventBus } from "../event_bus.js";
import { setText, qs, escapeHtml } from "../utils.js";
import { apiFetch } from "../api.js";

export function initEvaluation() {
  eventBus.on("language-changed", () => renderEvaluationPage());
}

export async function renderEvaluationPage() {
  if (appState.currentPage !== "evaluation") return;

  if (!appState.currentProjectId) {
    resetEvaluationMetrics();
    renderEvaluationPlots([]);
    return;
  }

  try {
    const data = await apiFetch(`/api/projects/${appState.currentProjectId}/evaluation`);
    const metrics = data.metrics || {};
    
    setText("#eval-map50", data.has_metrics ? formatMetric(metrics.map50, 3) : "--");
    setText("#eval-iou", data.has_metrics ? formatMetric(metrics.map50_95, 3) : "--");
    setText("#eval-precision", data.has_metrics ? formatMetric(metrics.precision, 3) : "--");
    setText("#eval-recall", data.has_metrics ? formatMetric(metrics.recall, 3) : "--");
    setText("#eval-f1", data.has_metrics ? formatMetric(metrics.f1, 3) : "--");
    setText("#eval-cls-loss", data.has_metrics ? formatMetric(metrics.cls_loss, 4) : "--");
    setText("#eval-dfl-loss", data.has_metrics ? formatMetric(metrics.dfl_loss, 4) : "--");
    setText("#eval-box-loss", data.has_metrics ? formatMetric(metrics.box_loss, 4) : "--");

    renderEvaluationPlots(data.has_metrics ? data.plots || [] : [], data.run_id);
  } catch (err) {
    console.error("Failed to load evaluation metrics:", err);
    resetEvaluationMetrics();
    renderEvaluationPlots([]);
  }
}

function resetEvaluationMetrics() {
  ["#eval-map50", "#eval-iou", "#eval-precision", "#eval-recall", "#eval-f1", "#eval-cls-loss", "#eval-dfl-loss", "#eval-box-loss"].forEach((selector) => {
    setText(selector, "--");
  });
}

function formatMetric(value, digits = 3) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : "--";
}

function renderEvaluationPlots(plots = [], runId = null) {
  const plotsGrid = qs("#evaluation-plots-grid");
  if (!plotsGrid) return;
  if (!plots.length) {
    plotsGrid.innerHTML = `<div class="empty-state evaluation-wide-empty">${escapeHtml(t("evaluation.empty"))}</div>`;
    return;
  }

  const runParam = runId ? `&run_id=${encodeURIComponent(runId)}` : "";
  plotsGrid.innerHTML = plots.map((plot) => {
    const title = plot.replace(/\.(png|jpg|jpeg)$/i, "").replace(/_/g, " ");
    const src = `/api/projects/${encodeURIComponent(appState.currentProjectId)}/evaluation/plot/${encodeURIComponent(plot)}?t=${Date.now()}${runParam}`;
    return `
      <div class="evaluation-plot-card">
        <h3>${escapeHtml(title)}</h3>
        <div class="evaluation-plot-preview">
          <a href="${src}" class="evaluation-plot-download" target="_blank" download="${escapeHtml(plot)}" aria-label="Download ${escapeHtml(title)}">
            <i class="fa-solid fa-download"></i>
          </a>
          <img src="${src}" alt="${escapeHtml(plot)}">
        </div>
      </div>
    `;
  }).join("");
}
