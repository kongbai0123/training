import { eventBus } from "../event_bus.js";
import { appState, getProjectStatus } from "../state.js";
import { apiFetch } from "../api.js";
import { qs } from "../utils.js";

let loadedProjectId = null;

export function initExport() {
  qs("#btn-export-pt")?.addEventListener("click", exportModel);
  qs("#btn-export-onnx")?.addEventListener("click", exportModel);
  qs("#btn-export-report")?.addEventListener("click", generateReport);
  
  qs("#btn-refresh-export-models")?.addEventListener("click", () => {
    loadExportModels();
  });
  
  qs("#export-model-select")?.addEventListener("change", () => {
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
  const project = appState.currentProject;
  const status = getProjectStatus(project);
  
  const ptBtn = qs("#btn-export-pt");
  const onnxBtn = qs("#btn-export-onnx");

  const select = qs("#export-model-select");
  const hasSelected = select && select.value;
  const canExport = status.bestModelExists || hasSelected;
  
  if (ptBtn) ptBtn.disabled = !canExport;
  if (onnxBtn) onnxBtn.disabled = !canExport;
  
  const ptCard = ptBtn?.closest(".control-card");
  const onnxCard = onnxBtn?.closest(".control-card");
  
  if (ptCard) ptCard.classList.toggle("muted", !canExport);
  if (onnxCard) onnxCard.classList.toggle("muted", !canExport);
}

async function loadExportModels() {
  const select = qs("#export-model-select");
  if (!select) return;

  if (!appState.currentProjectId) {
    select.innerHTML = '<option value="">-- 請先載入專案 --</option>';
    return;
  }

  try {
    const models = await apiFetch(`/api/projects/${appState.currentProjectId}/models`);
    select.innerHTML = '<option value="">-- 使用預設最佳模型 --</option>';
    if (Array.isArray(models) && models.length > 0) {
      models.forEach(m => {
        const opt = document.createElement("option");
        opt.value = m.model_id;
        opt.textContent = `${m.run_id} / ${m.weight_type}.pt (${m.task_type})`;
        select.appendChild(opt);
      });
    }
  } catch (err) {
    console.error("Failed to load export models", err);
    select.innerHTML = '<option value="">-- 載入選單失敗 --</option>';
  }
  updateButtonStates();
}

async function exportModel() {
  const select = qs("#export-model-select");
  const selectedModelId = select ? select.value : "";
  let url = `/api/projects/${appState.currentProjectId}/export`;
  if (selectedModelId) {
    url += `?model_id=${encodeURIComponent(selectedModelId)}`;
  }

  try {
    eventBus.emit("toast", "正在打包匯出模型檔案...");
    const data = await apiFetch(url);
    eventBus.emit("toast", `匯出成功：${data.onnx_path || data.pt_path || "exported"}`);
  } catch (err) {
    eventBus.emit("toast", `匯出失敗：${err.message}`);
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
  const a = document.createElement("a");
  a.href = url;
  a.download = `${project.project_name || "vision_training"}_report.md`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
