import { eventBus } from "../event_bus.js";
import { appState, getProjectStatus } from "../state.js";
import { apiFetch } from "../api.js";
import { qs } from "../utils.js";

export function initExport() {
  qs("#btn-export-pt")?.addEventListener("click", exportModel);
  qs("#btn-export-onnx")?.addEventListener("click", exportModel);
  qs("#btn-export-report")?.addEventListener("click", generateReport);
}

export function renderExportPage() {
  const project = appState.currentProject;
  const status = getProjectStatus(project);
  
  const ptBtn = qs("#btn-export-pt");
  const onnxBtn = qs("#btn-export-onnx");

  const hasModel = status.bestModelExists;
  
  if (ptBtn) ptBtn.disabled = !hasModel;
  if (onnxBtn) onnxBtn.disabled = !hasModel;
  
  const ptCard = ptBtn?.closest(".control-card");
  const onnxCard = onnxBtn?.closest(".control-card");
  
  if (ptCard) ptCard.classList.toggle("muted", !hasModel);
  if (onnxCard) onnxCard.classList.toggle("muted", !hasModel);
}

async function exportModel() {
  try {
    const data = await apiFetch(`/api/projects/${appState.currentProjectId}/export`);
    eventBus.emit("toast", `匯出完成：${data.onnx_path || data.pt_path || "exported"}`);
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
