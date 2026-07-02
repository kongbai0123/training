import { appState, t } from "../state.js";
import { eventBus } from "../event_bus.js";
import { setText, qs, escapeHtml } from "../utils.js";
import { apiFetch } from "../api.js";

export function initEvaluation() {
  eventBus.on("language-changed", () => renderEvaluationPage());
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeEvaluationPlotPreview();
  });
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
        <div class="evaluation-plot-preview" data-evaluation-plot-preview="${escapeHtml(src)}" data-evaluation-plot-title="${escapeHtml(title)}" role="button" tabindex="0" aria-label="Preview ${escapeHtml(title)}">
          <a href="${src}" class="evaluation-plot-download" target="_blank" download="${escapeHtml(plot)}" aria-label="Download ${escapeHtml(title)}">
            <i class="fa-solid fa-download"></i>
          </a>
          <img src="${src}" alt="${escapeHtml(plot)}">
        </div>
      </div>
    `;
  }).join("");
  plotsGrid.querySelectorAll("[data-evaluation-plot-preview]").forEach((preview) => {
    preview.addEventListener("click", (event) => {
      if (event.target.closest(".evaluation-plot-download")) return;
      openEvaluationPlotPreview(preview.dataset.evaluationPlotPreview, preview.dataset.evaluationPlotTitle);
    });
    preview.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      openEvaluationPlotPreview(preview.dataset.evaluationPlotPreview, preview.dataset.evaluationPlotTitle);
    });
  });
}

function openEvaluationPlotPreview(src, title) {
  if (!src) return;
  let modal = qs("#evaluation-plot-modal");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "evaluation-plot-modal";
    modal.className = "evaluation-plot-modal hidden";
    modal.innerHTML = `
      <div class="evaluation-plot-modal-backdrop" data-evaluation-plot-close></div>
      <div class="evaluation-plot-modal-content" role="dialog" aria-modal="true" aria-labelledby="evaluation-plot-modal-title">
        <div class="evaluation-plot-modal-header">
          <h2 id="evaluation-plot-modal-title"></h2>
          <button type="button" class="icon-btn evaluation-plot-modal-close" data-evaluation-plot-close aria-label="Close preview">&times;</button>
        </div>
        <div class="evaluation-plot-modal-body">
          <img id="evaluation-plot-modal-img" alt="">
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    modal.querySelectorAll("[data-evaluation-plot-close]").forEach((button) => {
      button.addEventListener("click", closeEvaluationPlotPreview);
    });
  }
  setText("#evaluation-plot-modal-title", title || "Evaluation Plot");
  const image = qs("#evaluation-plot-modal-img");
  if (image) {
    image.src = src;
    image.alt = title || "Evaluation Plot";
  }
  modal.classList.remove("hidden");
}

function closeEvaluationPlotPreview() {
  qs("#evaluation-plot-modal")?.classList.add("hidden");
}
