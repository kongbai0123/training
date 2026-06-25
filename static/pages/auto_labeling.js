import { appState, t } from "../state.js";
import { apiFetch } from "../api.js";
import { eventBus } from "../event_bus.js";
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
  eventBus.on("language-changed", () => renderAutoLabelingPage());
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
      status.textContent = t("autoLabel.toast.invalidModel");
      registerButton?.setAttribute("disabled", "disabled");
      showToast(t("autoLabel.toast.invalidModel"));
      return;
    }
    status.textContent = `${name} (${formatBytes(file.size)}) ${t("autoLabel.toast.selectedModel")}`;
    registerButton?.setAttribute("disabled", "disabled");
    showToast(t("autoLabel.toast.selectedModel"));
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
        <strong>${escapeHtml(t("autoLabel.modelLoadFailed"))}</strong>
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
    reason.textContent = t("autoLabel.startReason.noProject");
    return;
  }
  if (!status?.hasDataset) {
    reason.textContent = t("autoLabel.startReason.noDataset");
    return;
  }
  if (!(appState.models || []).length) {
    reason.textContent = t("autoLabel.startReason.noModel");
    return;
  }
  reason.textContent = t("autoLabel.startReason.apiPending");
}

function renderAutoLabelModelList(status = null) {
  const container = qs("#auto-label-model-list");
  if (!container) return;

  if (!appState.currentProjectId) {
    setHTML("#auto-label-model-list", `<div class="empty-state">${escapeHtml(t("autoLabel.startReason.noProject"))}</div>`);
    return;
  }

  if (loadingModels) {
    setHTML("#auto-label-model-list", `<div class="empty-state">${escapeHtml(t("autoLabel.modelLoading"))}</div>`);
    return;
  }

  const models = appState.models || [];
  ensureSelectedModel();

  if (!models.length) {
    setHTML("#auto-label-model-list", `
      <div class="empty-state">
        <strong>${escapeHtml(t("autoLabel.noWeights"))}</strong>
        <p>${escapeHtml(t("autoLabel.noWeightsHelp"))}</p>
      </div>
    `);
    return;
  }

  const projectTask = status?.taskType || appState.currentProject?.task_type || "";
  const groups = [
    ["best", t("autoLabel.model.best"), t("autoLabel.model.bestHelp")],
    ["last", t("autoLabel.model.last"), t("autoLabel.model.lastHelp")],
    ["other", t("autoLabel.model.other"), t("autoLabel.model.otherHelp")],
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
    ? (weightType === "last" ? t("autoLabel.model.checkpoint") : t("autoLabel.model.recommended"))
    : t("autoLabel.model.mismatch");
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
