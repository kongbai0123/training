import { appState } from "../state.js";
import { qs, setText } from "../utils.js";

export function renderHeaderStatus() {
  const health = appState.systemHealth || {};
  const device = health.device || {};
  const memory = health.memory || {};
  const hasGpu = device.has_gpu === true;
  const isHealthy = health.status === "healthy";

  setText("#header-gpu-value", hasGpu ? (device.device_name || "GPU ready") : "CPU mode");
  if (memory.status === "available" && memory.available_gb !== null && memory.available_gb !== undefined) {
    setText("#header-ram-value", `${memory.available_gb} GB free`);
  } else {
    setText("#header-ram-value", "Unavailable");
  }
  setText("#header-health-label", isHealthy ? "Healthy" : "Offline");
  setText("#header-project-title", appState.currentProject?.project_name || "No project opened");

  const dot = qs("#api-status-dot");
  if (dot) {
    dot.classList.toggle("online", isHealthy);
    dot.classList.toggle("offline", !isHealthy);
  }

  const saveBtn = qs("#btn-header-save-project");
  if (saveBtn) {
    saveBtn.disabled = !appState.currentProjectId;
    saveBtn.classList.toggle("btn-disabled", !appState.currentProjectId);
  }
}
