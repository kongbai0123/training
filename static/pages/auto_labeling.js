import { appState } from "../state.js";
import { apiFetch } from "../api.js";
import { qs, qsa, setHTML, escapeHtml } from "../utils.js";

let selectedAutoLabelModelId = "";
let loadedProjectId = null;
let loadingModels = false;

export function initAutoLabeling() {
  qs("#btn-refresh-auto-label-models")?.addEventListener("click", () => loadAutoLabelModels(true));

  qsa("[data-auto-source]").forEach((button) => {
    button.addEventListener("click", () => {
      qsa("[data-auto-source]").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
    });
  });

  qsa("input[name='auto-label-mode']").forEach((input) => {
    input.addEventListener("change", () => {
      qsa(".mode-card").forEach((card) => card.classList.remove("selected"));
      input.closest(".mode-card")?.classList.add("selected");
    });
  });
}

export function renderAutoLabelingPage(status) {
  if (!qs("#page-auto-labeling")) return;

  if (status.hasProject && loadedProjectId !== appState.currentProjectId && !loadingModels) {
    loadAutoLabelModels(false);
  }

  renderAutoLabelModelList(status);
}

async function loadAutoLabelModels(force) {
  if (!appState.currentProjectId) {
    appState.models = [];
    selectedAutoLabelModelId = "";
    loadedProjectId = null;
    renderAutoLabelModelList();
    return;
  }

  if (!force && loadedProjectId === appState.currentProjectId) return;

  loadingModels = true;
  renderAutoLabelModelList();
  try {
    const models = await apiFetch(`/api/projects/${appState.currentProjectId}/models`);
    appState.models = Array.isArray(models) ? models : [];
    loadedProjectId = appState.currentProjectId;
    ensureSelectedModel();
  } catch (err) {
    appState.models = [];
    selectedAutoLabelModelId = "";
    setHTML("#auto-label-model-list", `
      <div class="empty-state">
        <strong>Model Registry 載入失敗。</strong>
        <p>${escapeHtml(err.message)}</p>
      </div>
    `);
  } finally {
    loadingModels = false;
    renderAutoLabelModelList();
  }
}

function renderAutoLabelModelList(status = null) {
  const container = qs("#auto-label-model-list");
  if (!container) return;

  if (!appState.currentProjectId) {
    setHTML("#auto-label-model-list", `<div class="empty-state">請先建立或開啟專案。</div>`);
    return;
  }

  if (loadingModels) {
    setHTML("#auto-label-model-list", `<div class="empty-state">正在掃描可用模型權重...</div>`);
    return;
  }

  const models = appState.models || [];
  ensureSelectedModel();

  if (!models.length) {
    setHTML("#auto-label-model-list", `
      <div class="empty-state">
        <strong>No trained weights found.</strong>
        <p>請先完成 Training，讓 Model Registry 掃描到 best.pt 或 last.pt。</p>
      </div>
    `);
    return;
  }

  const projectTask = status?.taskType || appState.currentProject?.task_type || "";
  setHTML("#auto-label-model-list", models.map((model) => {
    const selected = model.model_id === selectedAutoLabelModelId ? "selected" : "";
    const compatible = isModelCompatible(projectTask, model.task_type);
    return `
      <button type="button" class="model-registry-item ${selected}" data-auto-model-id="${escapeHtml(model.model_id)}">
        <div class="model-registry-main">
          <strong>${escapeHtml(model.run_id || "--")} / ${escapeHtml(model.weight_type || "--")}.pt</strong>
          <span>${escapeHtml(model.task_type || "--")} · ${escapeHtml(formatDate(model.created_at))}</span>
        </div>
        <div class="model-registry-metrics">
          <span>mAP50(M): ${formatMetric(model.best_map50_m)}</span>
          <span>mAP50-95(M): ${formatMetric(model.best_map50_95_m)}</span>
          <span>${formatBytes(model.file_size)}</span>
          <span class="status-badge ${compatible ? "success" : "warning"}">${compatible ? "Draft ready" : "Task mismatch"}</span>
        </div>
      </button>
    `;
  }).join(""));

  qsa("[data-auto-model-id]").forEach((button) => {
    button.addEventListener("click", () => {
      selectedAutoLabelModelId = button.dataset.autoModelId;
      renderAutoLabelModelList(status);
    });
  });
}

function ensureSelectedModel() {
  const models = appState.models || [];
  if (models.length && !models.some((model) => model.model_id === selectedAutoLabelModelId)) {
    selectedAutoLabelModelId = models[0].model_id;
  }
}

function isModelCompatible(projectTask = "", modelTask = "") {
  const project = String(projectTask || "").toLowerCase();
  const model = String(modelTask || "").toLowerCase();
  if (!project || !model) return true;
  if (project.includes("segmentation")) return model.includes("segmentation");
  if (project.includes("detection")) return model.includes("detection");
  if (project.includes("classification")) return model.includes("classification");
  return true;
}

function formatMetric(value) {
  return value === null || value === undefined ? "--" : Number(value).toFixed(3);
}

function formatBytes(bytes) {
  const n = Number(bytes || 0);
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value) {
  if (!value) return "--";
  return String(value).replace("T", " ").slice(0, 19);
}
