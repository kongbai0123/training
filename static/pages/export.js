import { eventBus } from "../event_bus.js";
import { appState, getProjectStatus, t } from "../state.js";
import { apiFetch } from "../api.js";
import { qs, qsa } from "../utils.js";

let loadedProjectId = null;
let exportModels = [];

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
    updateButtonStates();
  });
}

export function renderExportPage() {
  if (appState.currentPage !== "export") return;

  updateButtonStates();

  if (appState.currentProjectId && loadedProjectId !== appState.currentProjectId) {
    loadExportModels().then(() => {
      loadedProjectId = appState.currentProjectId;
    });
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
    eventBus.emit("toast", t("export.toast.done", {
      path: data.package_path || data.contract_path || data.onnx_path || data.pt_path || "exported"
    }));
  } catch (err) {
    eventBus.emit("toast", t("export.toast.failed", { message: err.message }));
  }
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
