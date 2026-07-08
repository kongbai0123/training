import { appState, t } from "../state.js";
import { qs, setText } from "../utils.js";

export function renderHeaderStatus() {
  const health = appState.systemHealth || {};
  const device = health.device || {};
  const memory = health.memory || {};
  const hasGpu = device.has_gpu === true;
  const isHealthy = health.status === "healthy";

  setText("#header-gpu-value", hasGpu ? (device.device_name || t("header.gpuReady")) : t("header.cpuMode"));
  if (memory.status === "available" && memory.available_gb !== null && memory.available_gb !== undefined) {
    setText("#header-ram-value", t("header.ramFree", { value: memory.available_gb }));
  } else {
    setText("#header-ram-value", t("common.unavailable"));
  }
  setText("#header-health-label", isHealthy ? t("common.healthy") : t("common.offline"));
  setText("#header-project-title", appState.currentProject?.project_name || t("common.noProjectOpened"));

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
