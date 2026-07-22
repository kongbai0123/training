import { appState, t } from "../state.js";
import { eventBus } from "../event_bus.js";
import { setText, qs, escapeHtml } from "../utils.js";
import { apiFetch } from "../api.js";

let loadedEvaluationProjectId = "";
let cachedEvaluation = null;
let evaluationLoading = false;

export function initEvaluation() {
  eventBus.on("language-changed", () => renderEvaluationPage());
  eventBus.on("refresh-project", () => {
    loadedEvaluationProjectId = "";
    cachedEvaluation = null;
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeEvaluationPlotPreview();
  });
}

export async function renderEvaluationPage() {
  if (appState.currentPage !== "evaluation") return;

  if (!appState.currentProjectId) {
    loadedEvaluationProjectId = "";
    cachedEvaluation = null;
    resetEvaluationMetrics();
    renderEvaluationAssessment(null);
    renderEvaluationPlots([]);
    return;
  }

  if (loadedEvaluationProjectId === appState.currentProjectId && cachedEvaluation) {
    renderEvaluationData(cachedEvaluation);
    return;
  }
  if (evaluationLoading) return;

  const projectId = appState.currentProjectId;
  evaluationLoading = true;
  try {
    const data = await apiFetch(`/api/projects/${projectId}/evaluation`);
    if (appState.currentProjectId !== projectId) return;
    loadedEvaluationProjectId = projectId;
    cachedEvaluation = data;
    renderEvaluationData(data);
  } catch (err) {
    console.error("Failed to load evaluation metrics:", err);
    resetEvaluationMetrics();
    renderEvaluationAssessment(null);
    renderEvaluationPlots([]);
  } finally {
    evaluationLoading = false;
  }
}

function renderEvaluationData(data) {
  const metrics = data.metrics || {};
  setText("#eval-map50", data.has_metrics ? formatMetric(metrics.map50, 3) : "--");
  setText("#eval-iou", data.has_metrics ? formatMetric(metrics.map50_95, 3) : "--");
  setText("#eval-precision", data.has_metrics ? formatMetric(metrics.precision, 3) : "--");
  setText("#eval-recall", data.has_metrics ? formatMetric(metrics.recall, 3) : "--");
  setText("#eval-f1", data.has_metrics ? formatMetric(metrics.f1, 3) : "--");
  setText("#eval-cls-loss", data.has_metrics ? formatMetric(metrics.cls_loss, 4) : "--");
  setText("#eval-dfl-loss", data.has_metrics ? formatMetric(metrics.dfl_loss, 4) : "--");
  setText("#eval-box-loss", data.has_metrics ? formatMetric(metrics.box_loss, 4) : "--");
  renderEvaluationAssessment(data.assessment);
  renderEvaluationPlots(data.has_metrics ? data.plots || [] : [], data.run_id, data.plot_exports || {});
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

function renderEvaluationAssessment(assessment) {
  const empty = qs("#evaluation-assessment-empty");
  const content = qs("#evaluation-assessment-content");
  const hasAssessment = Boolean(assessment?.context && Array.isArray(assessment?.signals));
  empty?.classList.toggle("hidden", hasAssessment);
  content?.classList.toggle("hidden", !hasAssessment);
  setText("#evaluation-score", hasAssessment ? assessment.score : "--");
  if (!hasAssessment) return;

  const verdict = String(assessment.verdict || "attention");
  const verdictNode = qs("#evaluation-verdict");
  if (verdictNode) {
    verdictNode.className = `status-badge ${verdict}`;
    verdictNode.textContent = t(`evaluation.verdict.${verdict}`);
  }
  setText("#evaluation-assessment-summary", t(`evaluation.verdict.${verdict}.summary`));

  const context = assessment.context || {};
  const contextItems = [
    ["model", context.model],
    ["task", context.task_type],
    ["epochs", `${context.completed_epochs || 0} / ${context.configured_epochs || "--"}`],
    ["bestEpoch", context.best_epoch || "--"],
    ["imageSize", context.imgsz || "--"],
    ["batch", context.batch_size || "--"],
    ["dataset", context.total_images || "--"],
    ["classes", context.class_count || "--"],
  ];
  const chips = qs("#evaluation-context-chips");
  if (chips) {
    chips.innerHTML = contextItems.map(([key, value]) => `<span class="evaluation-context-chip">${escapeHtml(t(`evaluation.context.${key}`))}: ${escapeHtml(String(value))}</span>`).join("");
  }

  const recommendations = qs("#evaluation-recommendation-list");
  if (recommendations) {
    recommendations.innerHTML = assessment.signals.map((signal) => {
      const severity = ["critical", "warning", "info", "positive"].includes(signal.severity) ? signal.severity : "info";
      const icon = severity === "critical" ? "fa-circle-exclamation" : severity === "warning" ? "fa-triangle-exclamation" : severity === "positive" ? "fa-circle-check" : "fa-lightbulb";
      return `<article class="evaluation-recommendation ${severity}"><i class="fa-solid ${icon}"></i><div><strong>${escapeHtml(t(`evaluation.signal.${signal.code}.title`))}</strong><p>${escapeHtml(t(`evaluation.signal.${signal.code}.detail`, signal.values || {}))}</p></div></article>`;
    }).join("");
  }
}

function renderEvaluationPlots(plots = [], runId = null, plotExports = {}) {
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
    const vectorFilename = plotExports[plot] || "";
    const downloadFilename = vectorFilename || plot;
    const downloadFormat = vectorFilename ? "SVG" : pathExtensionLabel(plot);
    const downloadSrc = `/api/projects/${encodeURIComponent(appState.currentProjectId)}/evaluation/plot/${encodeURIComponent(downloadFilename)}/save-to-downloads${runId ? `?run_id=${encodeURIComponent(runId)}` : ""}`;
    const downloadTitle = vectorFilename ? t("evaluation.plot.downloadSvg") : t("evaluation.plot.downloadLegacyRaster");
    return `
      <div class="evaluation-plot-card">
        <h3>${escapeHtml(title)}</h3>
        <div class="evaluation-plot-preview" data-evaluation-plot-preview="${escapeHtml(src)}" data-evaluation-plot-title="${escapeHtml(title)}" role="button" tabindex="0" aria-label="Preview ${escapeHtml(title)}">
          <button type="button" class="evaluation-plot-download" data-evaluation-plot-download="${escapeHtml(downloadSrc)}" data-evaluation-plot-filename="${escapeHtml(downloadFilename)}" aria-label="${escapeHtml(downloadTitle)}: ${escapeHtml(title)}" title="${escapeHtml(downloadTitle)}">
            <i class="fa-solid fa-download"></i><span>${escapeHtml(downloadFormat)}</span>
          </button>
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
  plotsGrid.querySelectorAll("[data-evaluation-plot-download]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      await downloadEvaluationPlot(button.dataset.evaluationPlotDownload, button.dataset.evaluationPlotFilename);
    });
  });
}

function pathExtensionLabel(filename) {
  const extension = String(filename || "").split(".").pop()?.toUpperCase();
  return extension || "FILE";
}

async function downloadEvaluationPlot(url, filename) {
  if (!url) return;
  try {
    const result = await apiFetch(url, { method: "POST" });
    eventBus.emit("toast", t("evaluation.plot.savedToDownloads", {
      filename: result.filename || filename || "evaluation_plot.svg",
      path: result.saved_path || "",
    }));
  } catch (err) {
    eventBus.emit("toast", t("evaluation.plot.downloadFailed", { message: err.message }));
  }
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
