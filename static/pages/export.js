import { eventBus } from "../event_bus.js";
import { appState, getProjectStatus, t } from "../state.js";
import { apiFetch } from "../api.js";
import { qs } from "../utils.js";

let loadedProjectId = null;

export function initExport() {
  qs("#btn-export-pt")?.addEventListener("click", exportModel);
  qs("#btn-export-onnx")?.addEventListener("click", exportModel);
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
  updateButtonStates();

  if (appState.currentProjectId && loadedProjectId !== appState.currentProjectId) {
    loadExportModels().then(() => {
      loadedProjectId = appState.currentProjectId;
    });
  }
}

function updateButtonStates() {
  const status = getProjectStatus(appState.currentProject);
  const ptBtn = qs("#btn-export-pt");
  const onnxBtn = qs("#btn-export-onnx");
  const select = qs("#export-model-select");
  const hasSelected = Boolean(select?.value);
  const canExport = Boolean(status.bestModelExists || hasSelected);

  if (ptBtn) ptBtn.disabled = !canExport;
  if (onnxBtn) onnxBtn.disabled = !canExport;

  ptBtn?.closest(".control-card")?.classList.toggle("muted", !canExport);
  onnxBtn?.closest(".control-card")?.classList.toggle("muted", !canExport);
}

async function loadExportModels() {
  const select = qs("#export-model-select");
  if (!select) return;

  if (!appState.currentProjectId) {
    select.innerHTML = `<option value="">${t("export.selectProjectFirst")}</option>`;
    return;
  }

  try {
    const models = await apiFetch(`/api/projects/${appState.currentProjectId}/models`);
    select.innerHTML = `<option value="">${t("export.selectPlaceholder")}</option>`;
    if (Array.isArray(models) && models.length > 0) {
      models.forEach((model) => {
        const option = document.createElement("option");
        option.value = model.model_id;
        option.textContent = `${model.run_id} / ${model.weight_type}.pt (${model.task_type})`;
        select.appendChild(option);
      });
    }
  } catch (err) {
    console.error("Failed to load export models", err);
    select.innerHTML = `<option value="">${t("export.selectFailed")}</option>`;
  }
  updateButtonStates();
}

async function exportModel() {
  const selectedModelId = qs("#export-model-select")?.value || "";
  let url = `/api/projects/${appState.currentProjectId}/export`;
  if (selectedModelId) url += `?model_id=${encodeURIComponent(selectedModelId)}`;

  try {
    eventBus.emit("toast", t("export.toast.running"));
    const data = await apiFetch(url);
    eventBus.emit("toast", t("export.toast.done", {
      path: data.onnx_path || data.pt_path || "exported"
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
