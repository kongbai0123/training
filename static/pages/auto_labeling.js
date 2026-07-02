import { appState, t } from "../state.js";
import { apiFetch } from "../api.js";
import { eventBus } from "../event_bus.js";
import { qs, qsa, setHTML, setText, escapeHtml, showToast } from "../utils.js";

let selectedAutoLabelModelId = "";
let selectedModelSource = "project";
let loadedProjectId = null;
let loadingModels = false;
let weightManagerFilter = "all";
let weightManagerSort = "newest";
let selectedWeightIds = new Set();
let pendingDeleteWeightIds = [];

export function initAutoLabeling() {
  qs("#btn-refresh-auto-label-models")?.addEventListener("click", () => loadAutoLabelModels(true));
  initWeightManager();
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

function initWeightManager() {
  qs("#btn-open-weight-manager")?.addEventListener("click", openWeightManager);
  qs("#btn-close-weight-manager")?.addEventListener("click", closeWeightManager);
  qs("#btn-cancel-weight-manager")?.addEventListener("click", closeWeightManager);

  qs("#btn-weight-manager-refresh")?.addEventListener("click", async () => {
    hideWeightDeleteConfirmation();
    await loadAutoLabelModels(true);
    renderWeightManager();
  });

  qs("#weight-manager-filter")?.addEventListener("change", (event) => {
    weightManagerFilter = event.target.value || "all";
    hideWeightDeleteConfirmation();
    renderWeightManager();
  });

  qs("#weight-manager-sort")?.addEventListener("change", (event) => {
    weightManagerSort = event.target.value || "newest";
    hideWeightDeleteConfirmation();
    renderWeightManager();
  });

  qs("#btn-weight-manager-select-old-checkpoints")?.addEventListener("click", () => {
    const visible = getVisibleWeightModels();
    selectedWeightIds = new Set(
      visible
        .filter((model) => String(model.weight_type || "").toLowerCase() === "last")
        .map((model) => model.model_id)
    );
    hideWeightDeleteConfirmation();
    renderWeightManager();
  });

  qs("#btn-delete-selected-weights")?.addEventListener("click", requestDeleteSelectedWeights);
  qs("#btn-cancel-delete-weights")?.addEventListener("click", hideWeightDeleteConfirmation);
  qs("#btn-confirm-delete-weights")?.addEventListener("click", confirmDeleteSelectedWeights);
}

async function openWeightManager() {
  if (!appState.currentProjectId) {
    showToast(t("autoLabel.startReason.noProject"));
    return;
  }
  selectedWeightIds = new Set();
  pendingDeleteWeightIds = [];
  hideWeightDeleteConfirmation();
  qs("#weight-manager-modal")?.removeAttribute("hidden");
  if (loadedProjectId !== appState.currentProjectId) {
    await loadAutoLabelModels(false);
  }
  renderWeightManager();
}

function closeWeightManager() {
  qs("#weight-manager-modal")?.setAttribute("hidden", "hidden");
  selectedWeightIds = new Set();
  pendingDeleteWeightIds = [];
  hideWeightDeleteConfirmation();
}

function getVisibleWeightModels() {
  const models = (appState.models || []).filter((model) => {
    const weightType = String(model.weight_type || "").toLowerCase();
    if (!["best", "last"].includes(weightType)) return false;
    return weightManagerFilter === "all" || weightType === weightManagerFilter;
  });
  models.sort((a, b) => {
    const left = String(a.created_at || "");
    const right = String(b.created_at || "");
    return weightManagerSort === "oldest" ? left.localeCompare(right) : right.localeCompare(left);
  });
  return models;
}

function renderWeightManager() {
  const list = qs("#weight-manager-list");
  const summary = qs("#weight-manager-summary");
  const deleteButton = qs("#btn-delete-selected-weights");
  if (!list || !summary || !deleteButton) return;

  const models = getVisibleWeightModels();
  const total = (appState.models || []).filter((model) => ["best", "last"].includes(String(model.weight_type || "").toLowerCase())).length;
  const selectedCount = selectedWeightIds.size;
  summary.textContent = `目前顯示 ${models.length} / ${total} 個 checkpoint；已選取 ${selectedCount} 個。`;
  deleteButton.disabled = selectedCount === 0;
  list.classList.toggle("model-registry-scroll", models.length > 5);

  if (!models.length) {
    setHTML("#weight-manager-list", `
      <div class="empty-state">
        <strong>沒有符合條件的權重檔</strong>
        <p>請調整 best.pt / last.pt 篩選條件，或先完成訓練產生 checkpoint。</p>
      </div>
    `);
    return;
  }

  setHTML("#weight-manager-list", models.map((model) => renderWeightManagerRow(model)).join(""));

  qsa("[data-weight-id]").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const modelId = checkbox.dataset.weightId || "";
      if (!modelId) return;
      if (checkbox.checked) {
        selectedWeightIds.add(modelId);
      } else {
        selectedWeightIds.delete(modelId);
      }
      hideWeightDeleteConfirmation();
      renderWeightManager();
    });
  });
}

function renderWeightManagerRow(model) {
  const weightType = String(model.weight_type || "").toLowerCase();
  const checked = selectedWeightIds.has(model.model_id) ? "checked" : "";
  const badge = weightType === "best" ? "建議模型" : "Checkpoint";
  return `
    <label class="weight-manager-row">
      <input type="checkbox" data-weight-id="${escapeHtml(model.model_id)}" ${checked}>
      <div class="weight-manager-row-main">
        <strong>${escapeHtml(model.run_id || "--")} / ${escapeHtml(weightType || "--")}.pt</strong>
        <span>${escapeHtml(model.task_type || "--")} · ${escapeHtml(formatDate(model.created_at))}</span>
      </div>
      <div class="weight-manager-row-meta">
        <span>mAP50(M): ${formatMetric(model.best_map50_m)}</span>
        <span>mAP50-95(M): ${formatMetric(model.best_map50_95_m)}</span>
        <span>${formatBytes(model.file_size)}</span>
        <span class="status-badge ${weightType === "best" ? "success" : "warning"}">${badge}</span>
      </div>
    </label>
  `;
}

function requestDeleteSelectedWeights() {
  pendingDeleteWeightIds = Array.from(selectedWeightIds);
  if (!pendingDeleteWeightIds.length) {
    showToast("請先勾選要刪除的權重檔。");
    return;
  }
  const panel = qs("#weight-delete-confirmation");
  const text = qs("#weight-delete-confirm-text");
  if (text) {
    text.textContent = `即將刪除 ${pendingDeleteWeightIds.length} 個 checkpoint 檔案。此操作不會刪除 run history、metrics 或 artifacts，但權重檔本身無法從此面板復原。`;
  }
  panel?.removeAttribute("hidden");
}

function hideWeightDeleteConfirmation() {
  qs("#weight-delete-confirmation")?.setAttribute("hidden", "hidden");
  pendingDeleteWeightIds = [];
}

async function confirmDeleteSelectedWeights() {
  if (!appState.currentProjectId || !pendingDeleteWeightIds.length) return;
  const confirmButton = qs("#btn-confirm-delete-weights");
  confirmButton?.setAttribute("disabled", "disabled");
  try {
    const result = await apiFetch(`/api/projects/${appState.currentProjectId}/models/weights/delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model_ids: pendingDeleteWeightIds,
        confirm: true,
      }),
    });
    const deletedCount = Array.isArray(result.deleted) ? result.deleted.length : 0;
    const skippedCount = Array.isArray(result.skipped) ? result.skipped.length : 0;
    showToast(`已刪除 ${deletedCount} 個權重檔${skippedCount ? `，略過 ${skippedCount} 個` : ""}。`);
    selectedWeightIds = new Set();
    hideWeightDeleteConfirmation();
    await loadAutoLabelModels(true);
    renderWeightManager();
  } catch (err) {
    showToast(err.message || "刪除權重失敗。");
  } finally {
    confirmButton?.removeAttribute("disabled");
  }
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
  const visibleModelCount = (appState.models || []).filter((model) => {
    const weightType = String(model.weight_type || "").toLowerCase();
    return weightType !== "last";
  }).length;
  setText("#auto-stat-unlabeled", appState.currentProjectId ? String(unlabeled) : "--");
  setText("#auto-stat-models", appState.currentProjectId ? String(visibleModelCount) : "--");
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
    ["other", t("autoLabel.model.other"), t("autoLabel.model.otherHelp")],
  ];

  const groupedHtml = groups.map(([type, title, description]) => {
    const groupModels = models.filter((model) => {
      const weightType = String(model.weight_type || "").toLowerCase();
      return type === "other" ? !["best", "last"].includes(weightType) : weightType === type;
    });
    if (!groupModels.length) return "";
    const scrollClass = groupModels.length > 5 ? " model-registry-scroll" : "";
    return `
      <div class="model-registry-group${scrollClass}">
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
