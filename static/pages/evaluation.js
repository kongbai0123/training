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
    renderEvaluationDiagnostics({}, {});
    renderEvaluationCapabilities(null, null, {});
    renderEvaluationPlots([], null, {}, false);
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
    renderEvaluationDiagnostics({}, {});
    renderEvaluationCapabilities(null, null, {});
    renderEvaluationPlots([], null, {}, false);
  } finally {
    evaluationLoading = false;
  }
}

function renderEvaluationData(data) {
  renderEvaluationMetrics(data.has_metrics ? data.metric_cards || [] : []);
  renderEvaluationCapabilities(data.architecture, data.task_type, data.capabilities || {});
  renderEvaluationDiagnostics(data.diagnostics || {}, data.capabilities || {});
  renderEvaluationAssessment(data.assessment);
  renderEvaluationPlots(data.has_metrics ? data.plots || [] : [], data.run_id, data.plot_exports || {}, Boolean(data.has_metrics));
}

function resetEvaluationMetrics() {
  renderEvaluationMetrics([]);
}

function renderEvaluationMetrics(cards = []) {
  const grid = qs("#evaluation-metric-grid");
  if (!grid) return;
  if (!cards.length) {
    grid.innerHTML = `<div class="empty-state evaluation-wide-empty">${escapeHtml(t("evaluation.empty"))}</div>`;
    return;
  }
  grid.innerHTML = cards.map((card) => `
    <article class="metric-card" data-metric-key="${escapeHtml(card.key || "")}">
      <span>${escapeHtml(card.label || card.key || "Metric")}</span>
      <strong>${escapeHtml(formatMetric(card.value, metricDigits(card.value)))}</strong>
      <small>${escapeHtml(t(card.goal === "minimize" ? "evaluation.goal.minimize" : "evaluation.goal.maximize"))}</small>
    </article>
  `).join("");
}

function metricDigits(value) {
  const number = Math.abs(Number(value));
  return Number.isFinite(number) && number >= 100 ? 1 : 4;
}

function renderEvaluationCapabilities(architecture, taskType, capabilities = {}) {
  const host = qs("#evaluation-capability-summary");
  if (!host) return;
  if (!architecture) {
    host.innerHTML = "";
    return;
  }
  const labels = [
    t(`evaluation.architecture.${architecture}`),
    taskType || "--",
    capabilities.image_plots ? t("evaluation.capability.imagePlots") : null,
    capabilities.sequence_context ? t("evaluation.capability.sequence") : null,
    capabilities.row_context ? t("evaluation.capability.rows") : null,
  ].filter(Boolean);
  host.innerHTML = labels.map((label) => `<span>${escapeHtml(label)}</span>`).join("");
}

function renderEvaluationDiagnostics(diagnostics = {}, capabilities = {}) {
  const host = qs("#evaluation-diagnostics");
  const confusionCard = qs("#evaluation-confusion-card");
  const residualCard = qs("#evaluation-residual-card");
  const importanceCard = qs("#evaluation-importance-card");
  const hasConfusion = Boolean(capabilities.confusion_matrix);
  const hasResiduals = Boolean(capabilities.residual_analysis);
  const hasImportance = Boolean(capabilities.feature_importance);
  host?.classList.toggle("hidden", !hasConfusion && !hasResiduals && !hasImportance);
  confusionCard?.classList.toggle("hidden", !hasConfusion);
  residualCard?.classList.toggle("hidden", !hasResiduals);
  importanceCard?.classList.toggle("hidden", !hasImportance);
  if (hasConfusion) renderConfusionMatrix(diagnostics.confusion_labels || [], diagnostics.confusion_matrix || []);
  if (hasResiduals) renderResidualAnalysis(diagnostics.prediction_actual_samples || [], diagnostics.residuals || []);
  if (hasImportance) renderFeatureImportance(diagnostics.feature_importance || []);
}

function renderConfusionMatrix(labels, matrix) {
  const host = qs("#evaluation-confusion-content");
  if (!host) return;
  const safeLabels = labels.length ? labels : matrix.map((_, index) => String(index));
  host.innerHTML = `<div class="table-scroll"><table class="evaluation-confusion-table"><thead><tr><th>${escapeHtml(t("evaluation.diagnostics.actualPredicted"))}</th>${safeLabels.map((label) => `<th>${escapeHtml(label)}</th>`).join("")}</tr></thead><tbody>${matrix.map((row, index) => `<tr><th>${escapeHtml(safeLabels[index] ?? index)}</th>${row.map((value) => `<td>${escapeHtml(String(value ?? 0))}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

function renderResidualAnalysis(samples, residuals) {
  const host = qs("#evaluation-residual-content");
  if (!host) return;
  const values = residuals.map(Number).filter(Number.isFinite);
  const mean = values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
  const maxAbs = values.length ? Math.max(...values.map(Math.abs)) : null;
  host.innerHTML = `<div class="evaluation-context-chips"><span class="evaluation-context-chip">${escapeHtml(t("evaluation.diagnostics.meanResidual"))}: ${formatMetric(mean, 4)}</span><span class="evaluation-context-chip">${escapeHtml(t("evaluation.diagnostics.maxResidual"))}: ${formatMetric(maxAbs, 4)}</span></div><div class="table-scroll"><table class="evaluation-residual-table"><thead><tr><th>#</th><th>${escapeHtml(t("evaluation.diagnostics.actual"))}</th><th>${escapeHtml(t("evaluation.diagnostics.prediction"))}</th><th>${escapeHtml(t("evaluation.diagnostics.residual"))}</th></tr></thead><tbody>${samples.slice(0, 20).map((sample, index) => `<tr><td>${index + 1}</td><td>${formatMetric(sample.actual, 4)}</td><td>${formatMetric(sample.prediction, 4)}</td><td>${formatMetric(sample.residual, 4)}</td></tr>`).join("")}</tbody></table></div>`;
}

function renderFeatureImportance(items) {
  const host = qs("#evaluation-importance-content");
  if (!host) return;
  const rows = items.slice(0, 30);
  const max = Math.max(...rows.map((item) => Number(item.normalized_gain ?? item.gain ?? 0)), 0.000001);
  host.innerHTML = `<div class="evaluation-importance-list">${rows.map((item, index) => {
    const value = Number(item.normalized_gain ?? item.gain ?? 0);
    const width = Math.max(1, Math.min(100, (value / max) * 100));
    return `<div class="evaluation-importance-row"><strong>${escapeHtml(item.feature || `f${index}`)}</strong><span class="evaluation-importance-track"><i style="width:${width}%"></i></span><small>${formatMetric(value, 4)}</small></div>`;
  }).join("")}</div>`;
}

function formatMetric(value, digits = 3) {
  if (value === null || value === undefined || value === "") return "--";
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : "--";
}

function renderEvaluationAssessment(assessment) {
  const empty = qs("#evaluation-assessment-empty");
  const content = qs("#evaluation-assessment-content");
  const hasAssessment = Boolean(assessment?.context && Array.isArray(assessment?.signals));
  empty?.classList.toggle("hidden", hasAssessment);
  content?.classList.toggle("hidden", !hasAssessment);
  setText("#evaluation-score", hasAssessment && Number.isFinite(Number(assessment.score)) ? assessment.score : "--");
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
    ["primaryMetric", context.primary_metric],
    ["primaryValue", context.primary_value != null ? formatMetric(context.primary_value, 4) : null],
  ].filter(([, value]) => value !== undefined && value !== null && value !== "");
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

function renderEvaluationPlots(plots = [], runId = null, plotExports = {}, hasEvaluationData = false) {
  const plotsGrid = qs("#evaluation-plots-grid");
  if (!plotsGrid) return;
  if (!plots.length) {
    const messageKey = hasEvaluationData ? "evaluation.plots.unavailable" : "evaluation.empty";
    plotsGrid.innerHTML = `<div class="empty-state evaluation-wide-empty">${escapeHtml(t(messageKey))}</div>`;
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
