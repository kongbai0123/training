import { appState } from "../state.js";
import { apiFetch } from "../api.js";
import { qs, qsa, setHTML, setText, escapeHtml, showToast } from "../utils.js";

let selectedAutoLabelModelId = "";
let selectedModelSource = "project";
let loadedProjectId = null;
let loadingModels = false;

export function initAutoLabeling() {
  qs("#btn-refresh-auto-label-models")?.addEventListener("click", () => loadAutoLabelModels(true));
  initModelImportDropZone();
  initSourceOptions();
  initModelSourceTabs();
}

export function renderAutoLabelingPage(status) {
  if (!qs("#page-auto-labeling")) return;

  renderAutoLabelStats(status);

  if (status?.hasProject && loadedProjectId !== appState.currentProjectId && !loadingModels) {
    loadAutoLabelModels(false);
  }

  renderAutoLabelModelList(status);
  renderStartReason(status);
}

function initSourceOptions() {
  qsa("[data-auto-source]").forEach((button) => {
    button.addEventListener("click", () => {
      qsa("[data-auto-source]").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
    });
  });
}

function initModelSourceTabs() {
  qsa("[data-model-source]").forEach((button) => {
    button.addEventListener("click", () => {
      selectedModelSource = button.dataset.modelSource || "project";
      qsa("[data-model-source]").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      renderModelSourceVisibility();
    });
  });
  renderModelSourceVisibility();
}

function renderModelSourceVisibility() {
  const importPanel = qs(".model-import-collapse");
  const modelList = qs("#auto-label-model-list");
  if (!importPanel || !modelList) return;
  importPanel.open = selectedModelSource === "external";
  modelList.classList.toggle("dimmed", selectedModelSource !== "project");
}

function initModelImportDropZone() {
  const dropZone = qs("#auto-model-drop-zone");
  const fileInput = qs("#auto-model-file-input");
  const browseButton = qs("#btn-browse-auto-model");
  const registerButton = qs("#btn-register-auto-model");
  const status = qs("#auto-model-drop-status");
  if (!dropZone || !fileInput || !status) return;

  const updateSelectedModelFile = (file) => {
    if (!file) return;
    const name = String(file.name || "");
    if (!/\.(pt|onnx)$/i.test(name)) {
      status.textContent = "\u53ea\u63a5\u53d7 .pt \u6216 .onnx \u6a21\u578b\u6a94\u3002";
      registerButton?.setAttribute("disabled", "disabled");
      showToast("\u6a21\u578b\u532f\u5165\u53ea\u63a5\u53d7 .pt \u6216 .onnx \u6a94\u3002");
      return;
    }
    status.textContent = `${name} (${formatBytes(file.size)}) \u5df2\u9078\u64c7\uff0c\u7b49\u5f85\u5f8c\u7aef Register API\u3002`;
    registerButton?.setAttribute("disabled", "disabled");
    showToast("\u5df2\u9078\u64c7\u6a21\u578b\u6a94\uff1b\u76ee\u524d\u53ea\u5b8c\u6210\u532f\u5165 UI\uff0c\u5c1a\u672a\u5beb\u5165 Model Registry\u3002");
  };

  browseButton?.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => updateSelectedModelFile(fileInput.files?.[0]));

  ["dragenter", "dragover"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.add("drag-over");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.remove("drag-over");
    });
  });

  dropZone.addEventListener("drop", (event) => {
    updateSelectedModelFile(event.dataTransfer?.files?.[0]);
  });
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
        <strong>Model Registry \u8f09\u5165\u5931\u6557</strong>
        <p>${escapeHtml(err.message)}</p>
      </div>
    `);
  } finally {
    loadingModels = false;
    renderAutoLabelModelList();
    renderAutoLabelStats();
  }
}

function renderAutoLabelStats(status = null) {
  const imageCount = Number(status?.imageCount ?? appState.currentProject?.image_count ?? 0);
  const annotated = Number(status?.annotatedCount ?? appState.currentProject?.annotation_progress?.annotated ?? 0);
  const unlabeled = Math.max(0, imageCount - annotated);
  setText("#auto-stat-unlabeled", appState.currentProjectId ? String(unlabeled) : "--");
  setText("#auto-stat-models", appState.currentProjectId ? String((appState.models || []).length) : "--");
  setText("#auto-stat-drafts", "0");
  setText("#auto-stat-review", "0");
}

function renderStartReason(status = null) {
  const reason = qs("#auto-start-reason");
  if (!reason) return;
  if (!status?.hasProject) {
    reason.textContent = "\u8acb\u5148\u5efa\u7acb\u6216\u958b\u555f\u5c08\u6848\u3002";
    return;
  }
  if (!status?.hasDataset) {
    reason.textContent = "\u8acb\u5148\u5728 Dataset \u532f\u5165\u5f71\u50cf\u8cc7\u6599\u3002";
    return;
  }
  if (!(appState.models || []).length) {
    reason.textContent = "\u5c1a\u672a\u627e\u5230\u53ef\u7528\u6b0a\u91cd\uff1b\u8acb\u5148\u5b8c\u6210 Training\uff0c\u6216\u7b49\u5f85\u5916\u90e8\u6a21\u578b Register API\u3002";
    return;
  }
  reason.textContent = "\u5f8c\u7aef\u81ea\u52d5\u6a19\u8a3b API \u5c1a\u672a\u63a5\u5165\uff1b\u76ee\u524d\u5148\u5b8c\u6210\u5b89\u5168\u5de5\u4f5c\u6d41\u4ecb\u9762\u3002";
}

function renderAutoLabelModelList(status = null) {
  const container = qs("#auto-label-model-list");
  if (!container) return;

  if (!appState.currentProjectId) {
    setHTML("#auto-label-model-list", `<div class="empty-state">\u8acb\u5148\u5efa\u7acb\u6216\u958b\u555f\u5c08\u6848\u3002</div>`);
    return;
  }

  if (loadingModels) {
    setHTML("#auto-label-model-list", `<div class="empty-state">\u6b63\u5728\u6383\u63cf\u53ef\u7528\u6a21\u578b\u6b0a\u91cd...</div>`);
    return;
  }

  const models = appState.models || [];
  ensureSelectedModel();

  if (!models.length) {
    setHTML("#auto-label-model-list", `
      <div class="empty-state">
        <strong>No trained weights found.</strong>
        <p>\u8acb\u5148\u5b8c\u6210 Training\uff0cModel Registry \u624d\u80fd\u6383\u63cf best.pt \u6216 last.pt\u3002</p>
      </div>
    `);
    return;
  }

  const projectTask = status?.taskType || appState.currentProject?.task_type || "";
  const groups = [
    ["best", "Recommended project model (best.pt)", "\u9a57\u8b49\u8868\u73fe\u6700\u4f73\uff0c\u5efa\u8b70\u512a\u5148\u7528\u65bc\u81ea\u52d5\u6a19\u8a3b\u3002"],
    ["last", "Alternative checkpoint (last.pt)", "\u6700\u5f8c\u4e00\u6b21 checkpoint\uff0c\u9069\u5408\u6aa2\u67e5\u6700\u65b0\u8a13\u7df4\u72c0\u614b\uff0c\u4e0d\u4e00\u5b9a\u662f\u6700\u4f73\u6a21\u578b\u3002"],
    ["other", "Other weights", "\u5176\u4ed6\u53ef\u7528\u6b0a\u91cd\u3002"],
  ];

  const groupedHtml = groups.map(([type, title, description]) => {
    const groupModels = models.filter((model) => {
      const weightType = String(model.weight_type || "").toLowerCase();
      return type === "other" ? !["best", "last"].includes(weightType) : weightType === type;
    });
    if (!groupModels.length) return "";
    return `
      <div class="model-registry-group">
        <div class="model-registry-group-title">
          <strong>${escapeHtml(title)}</strong>
          <span>${description}</span>
        </div>
        ${groupModels.map((model) => renderModelButton(model, projectTask)).join("")}
      </div>
    `;
  }).join("");

  setHTML("#auto-label-model-list", groupedHtml);

  qsa("[data-auto-model-id]").forEach((button) => {
    button.addEventListener("click", () => {
      selectedAutoLabelModelId = button.dataset.autoModelId;
      renderAutoLabelModelList(status);
    });
  });
}

function renderModelButton(model, projectTask) {
  const selected = model.model_id === selectedAutoLabelModelId ? "selected" : "";
  const compatible = isModelCompatible(projectTask, model.task_type);
  const weightType = String(model.weight_type || "").toLowerCase();
  const badgeText = compatible
    ? (weightType === "last" ? "Checkpoint" : "Recommended")
    : "Task mismatch";
  return `
    <button type="button" class="model-registry-item ${selected} ${weightType === "last" ? "checkpoint" : ""}" data-auto-model-id="${escapeHtml(model.model_id)}">
      <div class="model-registry-main">
        <strong>${escapeHtml(model.run_id || "--")} / ${escapeHtml(model.weight_type || "--")}.pt</strong>
        <span>${escapeHtml(model.task_type || "--")} ? ${escapeHtml(formatDate(model.created_at))}</span>
      </div>
      <div class="model-registry-metrics">
        <span>mAP50(M): ${formatMetric(model.best_map50_m)}</span>
        <span>mAP50-95(M): ${formatMetric(model.best_map50_95_m)}</span>
        <span>${formatBytes(model.file_size)}</span>
        <span class="status-badge ${compatible ? "success" : "warning"}">${badgeText}</span>
      </div>
    </button>
  `;
}

function ensureSelectedModel() {
  const models = appState.models || [];
  if (models.length && !models.some((model) => model.model_id === selectedAutoLabelModelId)) {
    const best = models.find((model) => String(model.weight_type || "").toLowerCase() === "best");
    selectedAutoLabelModelId = (best || models[0]).model_id;
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
