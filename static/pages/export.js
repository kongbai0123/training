import { eventBus } from "../event_bus.js";
import { appState, getProjectStatus, t } from "../state.js";
import { apiFetch } from "../api.js";
import { escapeHtml, qs, qsa } from "../utils.js";

let loadedProjectId = null;
let exportModels = [];
let exportArtifacts = [];
let lastExportResult = null;

export function initExport() {
  qsa("[data-export-format]").forEach((button) => {
    button.addEventListener("click", () => exportModel(button.dataset.exportFormat || "auto"));
  });
  qsa("[data-export-report]").forEach((button) => {
    button.addEventListener("click", generateReport);
  });
  qs("#btn-export-report")?.addEventListener("click", generateReport);
  qs("#btn-refresh-export-models")?.addEventListener("click", () => loadExportModels());
  qs("#export-model-select")?.addEventListener("change", () => updateButtonStates());

  eventBus.on("language-changed", () => {
    loadedProjectId = null;
    loadExportModels();
    loadExportArtifacts();
    renderExportResult();
    renderExportArtifacts();
    updateButtonStates();
  });
}

export function renderExportPage() {
  if (appState.currentPage !== "export") return;

  updateButtonStates();

  if (appState.currentProjectId && loadedProjectId !== appState.currentProjectId) {
    lastExportResult = null;
    Promise.all([loadExportModels(), loadExportArtifacts()]).then(() => {
      loadedProjectId = appState.currentProjectId;
    });
  } else if (!appState.currentProjectId) {
    exportArtifacts = [];
    lastExportResult = null;
    renderExportResult();
    renderExportArtifacts();
  }
}

function updateButtonStates() {
  const status = getProjectStatus(appState.currentProject);
  const select = qs("#export-model-select");
  const hasSelected = Boolean(select?.value);
  const canExport = Boolean(status.bestModelExists || hasSelected || exportModels.length > 0);
  const isRnn = isRnnProject(appState.currentProject);
  const cnnActions = qs("#export-cnn-actions");
  const rnnActions = qs("#export-rnn-actions");

  if (cnnActions) cnnActions.hidden = isRnn;
  if (rnnActions) rnnActions.hidden = !isRnn;

  qsa("[data-export-format]").forEach((button) => {
    const visibleGroup = button.closest("#export-rnn-actions, #export-cnn-actions");
    const visible = !visibleGroup || !visibleGroup.hidden;
    button.disabled = !canExport || !visible;
    button.closest(".control-card")?.classList.toggle("muted", !canExport || !visible);
  });
}

function isRnnProject(project) {
  const taskType = String(project?.task_type || "").toLowerCase();
  const architecture = String(project?.architecture || project?.training_config?.architecture || "").toLowerCase();
  return architecture === "rnn" || taskType.startsWith("sequence_") || taskType.includes("time_series");
}

async function loadExportModels() {
  const select = qs("#export-model-select");
  if (!select) return;

  if (!appState.currentProjectId) {
    exportModels = [];
    select.innerHTML = `<option value="">${t("export.selectProjectFirst")}</option>`;
    updateButtonStates();
    return;
  }

  try {
    const models = await apiFetch(`/api/projects/${appState.currentProjectId}/models`);
    exportModels = Array.isArray(models) ? models : [];
    select.innerHTML = `<option value="">${t("export.selectPlaceholder")}</option>`;
    if (exportModels.length > 0) {
      exportModels.forEach((model) => {
        const option = document.createElement("option");
        option.value = model.model_id;
        option.textContent = `${model.run_id} / ${model.weight_type}.pt (${model.task_type})`;
        select.appendChild(option);
      });
    }
  } catch (err) {
    console.error("Failed to load export models", err);
    exportModels = [];
    select.innerHTML = `<option value="">${t("export.selectFailed")}</option>`;
  }
  updateButtonStates();
}

async function loadExportArtifacts() {
  if (!appState.currentProjectId) {
    exportArtifacts = [];
    renderExportResult();
    renderExportArtifacts();
    return;
  }

  try {
    const payload = await apiFetch(`/api/projects/${appState.currentProjectId}/exports?limit=12`);
    exportArtifacts = Array.isArray(payload?.exports) ? payload.exports : [];
  } catch (err) {
    console.error("Failed to load export artifacts", err);
    exportArtifacts = [];
  }
  renderExportResult();
  renderExportArtifacts();
}

async function exportModel(format = "auto") {
  const selectedModelId = qs("#export-model-select")?.value || "";
  const params = new URLSearchParams();
  if (selectedModelId) params.set("model_id", selectedModelId);
  if (format) params.set("format", format);
  const query = params.toString();
  const url = `/api/projects/${appState.currentProjectId}/export${query ? `?${query}` : ""}`;

  try {
    eventBus.emit("toast", t("export.toast.running"));
    const data = await apiFetch(url);
    lastExportResult = data;
    renderExportResult();
    await loadExportArtifacts();
    eventBus.emit("toast", t("export.toast.done", {
      path: resolveExportPath(data)
    }));
  } catch (err) {
    eventBus.emit("toast", t("export.toast.failed", { message: err.message }));
  }
}

function renderExportResult() {
  const panel = qs("#export-result-panel");
  const badge = qs("#export-result-badge");
  if (!panel) return;

  const result = lastExportResult || exportArtifacts[0] || null;
  if (!result) {
    panel.className = "export-result-panel empty";
    panel.textContent = t("export.noResult");
    if (badge) {
      badge.className = "summary-badge badge-neutral";
      badge.textContent = t("export.noExportBadge");
    }
    return;
  }

  panel.className = "export-result-panel";
  panel.innerHTML = `
    <div class="export-result-primary">
      <span class="summary-badge badge-success">${escapeHtml(formatExportType(result.export_type))}</span>
      <strong>${escapeHtml(result.export_id || t("export.lastExport"))}</strong>
      <code>${escapeHtml(resolveExportPath(result))}</code>
    </div>
    <div class="export-result-meta">
      <span>${escapeHtml(t("rnn.export.resultRun"))}: <strong>${escapeHtml(result.run_id || "--")}</strong></span>
      <span>${escapeHtml(t("rnn.export.resultCreated"))}: <strong>${escapeHtml(formatDateTime(result.created_at))}</strong></span>
      <span>${escapeHtml(t("export.summaryFile"))}: <code>${escapeHtml(result.summary_path || result.summary_abs_path || "--")}</code></span>
    </div>
  `;
  if (badge) {
    badge.className = "summary-badge badge-success";
    badge.textContent = t("export.exportedBadge");
  }
}

function renderExportArtifacts() {
  const list = qs("#export-artifact-list");
  const count = qs("#export-artifact-count");
  if (count) count.textContent = String(exportArtifacts.length);
  if (!list) return;
  list.innerHTML = renderExportArtifactList(exportArtifacts);
}

export function renderExportArtifactList(artifacts = []) {
  if (!artifacts.length) {
    return `<div class="summary-empty">${escapeHtml(t("export.noArtifacts"))}</div>`;
  }
  return artifacts.map((artifact) => `
    <article class="export-artifact-row">
      <div class="export-artifact-main">
        <span class="summary-badge badge-info">${escapeHtml(formatExportType(artifact.export_type))}</span>
        <strong>${escapeHtml(artifact.export_id || "--")}</strong>
        <code>${escapeHtml(resolveExportPath(artifact))}</code>
      </div>
      <div class="export-artifact-meta">
        <span>${escapeHtml(t("rnn.export.resultRun"))}: <strong>${escapeHtml(artifact.run_id || "--")}</strong></span>
        <span>${escapeHtml(t("rnn.export.resultCreated"))}: <strong>${escapeHtml(formatDateTime(artifact.created_at))}</strong></span>
        <span>${escapeHtml(t("export.files"))}: <strong>${escapeHtml(String(artifact.file_count ?? 0))}</strong></span>
      </div>
    </article>
  `).join("");
}

function resolveExportPath(data = {}) {
  return data.primary_abs_path
    || data.primary_path
    || data.package_abs_path
    || data.contract_abs_path
    || data.onnx_abs_path
    || data.pt_abs_path
    || data.package_path
    || data.contract_path
    || data.onnx_path
    || data.pt_path
    || "exported";
}

function formatExportType(type = "") {
  const labels = {
    cnn_onnx: "ONNX",
    cnn_pt_copy: "PT",
    rnn_model_package: t("export.rnnPackageTitle"),
    rnn_inference_contract: t("export.rnnContractTitle"),
    rnn_schema_scaler_package: t("export.rnnSchemaTitle"),
    export_artifact: t("export.artifact")
  };
  return labels[type] || String(type || t("export.artifact")).replaceAll("_", " ");
}

function formatDateTime(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function generateReport() {
  const project = appState.currentProject;
  if (!project) return;
  const status = getProjectStatus(project);
  const report = `# Vision Training Studio Report

- Project: ${project.project_name}
- Task type: ${project.task_type}
- Images: ${status.imageCount}
- Annotation progress: ${status.annotatedCount}/${status.imageCount}
- LabelMe backend: Connected
- Split: ${status.splitComplete ? "Ready" : "Not ready"}
- Training: ${status.trainingLabel}
`;
  const blob = new Blob([report], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${project.project_name || "vision_training"}_report.md`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
