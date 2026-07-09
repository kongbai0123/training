import { appState, t } from "../state.js";
import { apiFetch } from "../api.js";
import { eventBus } from "../event_bus.js";
import { qs, qsa, setHTML, setText, escapeHtml, showToast, collectDroppedFiles } from "../utils.js";

let selectedAutoLabelModelId = "";
let selectedAutoSource = "unlabeled";
let selectedModelSource = "project";
let loadedProjectId = null;
let loadingModels = false;
let autoLabelJobs = [];
let selectedAutoReviewItem = null;
let loadedAutoLabelStatusProjectId = null;
let loadingAutoLabelStatus = false;
let weightManagerFilter = "all";
let weightManagerSort = "newest";
let selectedWeightIds = new Set();
let pendingDeleteWeightIds = [];
let weightManagerModels = [];
let cleanupRunCandidates = [];
let selectedCleanupRunIds = new Set();
let pendingCleanupRunIds = [];

const AUTO_SOURCE_IMAGE_EXTENSIONS = new Set([".jpg", ".jpeg", ".png", ".bmp"]);
const AUTO_SOURCE_ZIP_EXTENSIONS = new Set([".zip"]);

export function classifyAutoLabelSourceFiles(files) {
  const result = {
    images: [],
    zips: [],
    rejected: [],
    extensionCounts: {},
  };
  [...(files || [])].forEach((file) => {
    const rawName = String(file?.webkitRelativePath || file?.name || "");
    const normalizedName = rawName.replaceAll("\\", "/");
    const basename = normalizedName.split("/").filter(Boolean).pop() || normalizedName;
    const match = basename.match(/(\.[^.]+)$/);
    const extension = match ? match[1].toLowerCase() : "";
    const normalizedExtension = extension || "(none)";
    result.extensionCounts[normalizedExtension] = (result.extensionCounts[normalizedExtension] || 0) + 1;
    if (AUTO_SOURCE_IMAGE_EXTENSIONS.has(extension)) {
      result.images.push(file);
    } else if (AUTO_SOURCE_ZIP_EXTENSIONS.has(extension)) {
      result.zips.push(file);
    } else {
      result.rejected.push({ file, extension: normalizedExtension, path: normalizedName });
    }
  });
  return result;
}

export function initAutoLabeling() {
  qs("#btn-refresh-auto-label-models")?.addEventListener("click", () => loadAutoLabelModels(true));
  qs("#btn-start-auto-label")?.addEventListener("click", createAutoLabelJob);
  qs("#btn-auto-review-accept")?.addEventListener("click", () => reviewSelectedAutoLabelItem("accept"));
  qs("#btn-auto-review-reject")?.addEventListener("click", () => reviewSelectedAutoLabelItem("reject"));
  qs("#btn-auto-review-accept-next")?.addEventListener("click", () => reviewSelectedAutoLabelItem("accept", { moveNext: true }));
  qs("#btn-auto-review-reject-next")?.addEventListener("click", () => reviewSelectedAutoLabelItem("reject", { moveNext: true }));
  qs("#btn-auto-review-skip")?.addEventListener("click", () => reviewSelectedAutoLabelItem("skip"));
  qs("#btn-auto-review-hard-case")?.addEventListener("click", () => reviewSelectedAutoLabelItem("hard_case"));
  qs("#btn-auto-review-edit")?.addEventListener("click", editSelectedAutoLabelItem);
  qs("#btn-auto-review-prev")?.addEventListener("click", () => navigateAutoReviewItem(-1));
  qs("#btn-auto-review-next")?.addEventListener("click", () => navigateAutoReviewItem(1));
  initWeightManager();
  initModelImportDropZone();
  initSourceDropZone();
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

  loadAutoLabelStatus(status);
  renderAutoLabelModelList(status);
  renderStartReason(status);
  renderAutoLabelJobHistory();
  renderAutoLabelReviewQueue();
}

function initSourceOptions() {
  qsa("[data-auto-source]").forEach((button) => {
    button.addEventListener("click", () => {
      selectedAutoSource = button.dataset.autoSource || "unlabeled";
      qsa("[data-auto-source]").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
    });
  });
}

function initSourceDropZone() {
  const dropZone = qs("#auto-source-drop-zone");
  if (!dropZone) return;

  const fileInput = document.createElement("input");
  fileInput.type = "file";
  fileInput.multiple = true;
  fileInput.accept = ".jpg,.jpeg,.png,.bmp,.zip";
  fileInput.hidden = true;
  fileInput.id = "auto-source-file-input";
  dropZone.parentNode?.insertBefore(fileInput, dropZone.nextSibling);

  dropZone.classList.remove("disabled-drop");
  dropZone.setAttribute("role", "button");
  dropZone.tabIndex = 0;
  dropZone.addEventListener("click", () => fileInput.click());
  dropZone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      fileInput.click();
    }
  });

  fileInput.addEventListener("change", async (event) => {
    await uploadAutoLabelSourceFiles([...(event.target.files || [])]);
    fileInput.value = "";
  });

  ["dragenter", "dragover"].forEach((name) => {
    dropZone.addEventListener(name, (event) => {
      event.preventDefault();
      event.stopPropagation();
      dropZone.classList.add("dz-drag-hover");
    }, true);
  });
  ["dragleave", "drop"].forEach((name) => {
    dropZone.addEventListener(name, (event) => {
      event.preventDefault();
      event.stopPropagation();
      dropZone.classList.remove("dz-drag-hover");
    }, true);
  });
  dropZone.addEventListener("drop", async (event) => {
    await uploadAutoLabelSourceFiles(await collectDroppedFiles(event.dataTransfer));
  }, true);
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
    await loadWeightManagerModels();
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
  qs("#btn-run-cleanup-refresh")?.addEventListener("click", loadRunCleanupCandidates);
  qs("#btn-cleanup-selected-runs")?.addEventListener("click", requestCleanupSelectedRuns);
  qs("#btn-cancel-cleanup-runs")?.addEventListener("click", hideRunCleanupConfirmation);
  qs("#btn-confirm-cleanup-runs")?.addEventListener("click", confirmCleanupSelectedRuns);
}

async function openWeightManager() {
  if (!appState.currentProjectId) {
    showToast(t("autoLabel.startReason.noProject"));
    return;
  }
  selectedWeightIds = new Set();
  pendingDeleteWeightIds = [];
  selectedCleanupRunIds = new Set();
  pendingCleanupRunIds = [];
  hideWeightDeleteConfirmation();
  hideRunCleanupConfirmation();
  qs("#weight-manager-modal")?.removeAttribute("hidden");
  if (loadedProjectId !== appState.currentProjectId) {
    await loadAutoLabelModels(false);
  }
  await loadWeightManagerModels();
  await loadRunCleanupCandidates();
  renderWeightManager();
}

function closeWeightManager() {
  qs("#weight-manager-modal")?.setAttribute("hidden", "hidden");
  selectedWeightIds = new Set();
  pendingDeleteWeightIds = [];
  selectedCleanupRunIds = new Set();
  pendingCleanupRunIds = [];
  hideWeightDeleteConfirmation();
  hideRunCleanupConfirmation();
}

function getVisibleWeightModels() {
  const models = (weightManagerModels || []).filter((model) => {
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
  const total = (weightManagerModels || []).filter((model) => ["best", "last"].includes(String(model.weight_type || "").toLowerCase())).length;
  const selectedCount = selectedWeightIds.size;
  summary.textContent = `目前顯示 ${models.length} / ${total} 個 checkpoint，已選取 ${selectedCount} 個。`;
  deleteButton.disabled = selectedCount === 0;
  list.classList.toggle("model-registry-scroll", models.length > 5);

  if (!models.length) {
    setHTML("#weight-manager-list", `
      <div class="empty-state">
        <strong>沒有符合條件的模型權重</strong>
        <p>請調整 best.pt / last.pt 篩選，或完成一次訓練後再管理 checkpoint。</p>
      </div>
    `);
  } else {
    setHTML("#weight-manager-list", models.map((model) => renderWeightManagerRow(model)).join(""));
  }

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

  renderRunCleanupCandidates();
}

function renderWeightManagerRow(model) {
  const weightType = String(model.weight_type || "").toLowerCase();
  const checked = selectedWeightIds.has(model.model_id) ? "checked" : "";
  const badge = weightType === "best" ? t("autoLabel.model.bestBadge") : t("autoLabel.model.checkpoint");
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
    showToast("請先選擇要刪除的權重檔。");
    return;
  }
  const panel = qs("#weight-delete-confirmation");
  const text = qs("#weight-delete-confirm-text");
  if (text) {
    text.textContent = `即將刪除 ${pendingDeleteWeightIds.length} 個 checkpoint 檔案。這不會刪除 run history、metrics 或 artifacts。`;
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
    showToast(`已刪除 ${deletedCount} 個權重${skippedCount ? `，略過 ${skippedCount} 個` : ""}。`);
    selectedWeightIds = new Set();
    hideWeightDeleteConfirmation();
    await loadAutoLabelModels(true);
    await loadWeightManagerModels();
    renderWeightManager();
  } catch (err) {
    showToast(err.message || "刪除權重失敗。");
  } finally {
    confirmButton?.removeAttribute("disabled");
  }
}

async function loadRunCleanupCandidates() {
  const summary = qs("#run-cleanup-summary");
  const list = qs("#run-cleanup-list");
  if (!appState.currentProjectId || !summary || !list) return;
  summary.textContent = "正在掃描測試 Run...";
  setHTML("#run-cleanup-list", `<div class="empty-state">正在讀取可清理的測試 Run。</div>`);
  try {
    const payload = await apiFetch(`/api/projects/${appState.currentProjectId}/runs/cleanup-candidates`, { suppressToast: true });
    cleanupRunCandidates = Array.isArray(payload.candidates) ? payload.candidates : [];
    selectedCleanupRunIds = new Set(Array.from(selectedCleanupRunIds).filter((runId) => cleanupRunCandidates.some((item) => item.run_id === runId)));
  } catch (err) {
    cleanupRunCandidates = [];
    summary.textContent = err.message || "掃描測試 Run 失敗。";
  }
  renderRunCleanupCandidates();
}

function renderRunCleanupCandidates() {
  const list = qs("#run-cleanup-list");
  const summary = qs("#run-cleanup-summary");
  const cleanupButton = qs("#btn-cleanup-selected-runs");
  if (!list || !summary || !cleanupButton) return;

  const selectedCount = selectedCleanupRunIds.size;
  summary.textContent = `找到 ${cleanupRunCandidates.length} 個可清理測試 Run，已選取 ${selectedCount} 個。`;
  cleanupButton.disabled = selectedCount === 0;
  list.classList.toggle("model-registry-scroll", cleanupRunCandidates.length > 5);

  if (!cleanupRunCandidates.length) {
    setHTML("#run-cleanup-list", `
      <div class="empty-state">
        <strong>沒有可清理的測試 Run</strong>
        <p>目前沒有 run_id 含 smoke / probe / test / workers0 / tmp / debug 的訓練紀錄。</p>
      </div>
    `);
    return;
  }

  setHTML("#run-cleanup-list", cleanupRunCandidates.map((run) => renderRunCleanupRow(run)).join(""));
  qsa("[data-cleanup-run-id]").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const runId = checkbox.dataset.cleanupRunId || "";
      if (!runId) return;
      if (checkbox.checked) {
        selectedCleanupRunIds.add(runId);
      } else {
        selectedCleanupRunIds.delete(runId);
      }
      hideRunCleanupConfirmation();
      renderRunCleanupCandidates();
    });
  });
}

function renderRunCleanupRow(run) {
  const checked = selectedCleanupRunIds.has(run.run_id) ? "checked" : "";
  const best = run.best?.exists ? "best.pt" : "no best.pt";
  const last = run.last?.exists ? "last.pt" : "no last.pt";
  return `
    <label class="weight-manager-row run-cleanup-row">
      <input type="checkbox" data-cleanup-run-id="${escapeHtml(run.run_id)}" ${checked}>
      <div class="weight-manager-row-main">
        <strong>${escapeHtml(run.run_id || "--")}</strong>
        <span>${escapeHtml(run.model || "--")} · ${escapeHtml(formatDate(run.completed_at || run.created_at))}</span>
      </div>
      <div class="weight-manager-row-meta">
        <span>${escapeHtml(best)}</span>
        <span>${escapeHtml(last)}</span>
        <span>${escapeHtml(t("autoLabel.cleanup.files", { count: Number(run.artifact_count || 0) }))}</span>
        <span class="status-badge warning">${escapeHtml(t("autoLabel.cleanup.testCandidate"))}</span>
      </div>
    </label>
  `;
}

function requestCleanupSelectedRuns() {
  pendingCleanupRunIds = Array.from(selectedCleanupRunIds);
  if (!pendingCleanupRunIds.length) {
    showToast("請先選擇要清理的測試 Run。");
    return;
  }
  const text = qs("#run-cleanup-confirm-text");
  if (text) {
    text.textContent = `即將清理 ${pendingCleanupRunIds.length} 個測試 Run。這會同步移除 project.json.training_runs、training/runs 內的 weights、metrics 與 artifacts。`;
  }
  qs("#run-cleanup-confirmation")?.removeAttribute("hidden");
}

function hideRunCleanupConfirmation() {
  qs("#run-cleanup-confirmation")?.setAttribute("hidden", "hidden");
  pendingCleanupRunIds = [];
}

async function confirmCleanupSelectedRuns() {
  if (!appState.currentProjectId || !pendingCleanupRunIds.length) return;
  const confirmButton = qs("#btn-confirm-cleanup-runs");
  confirmButton?.setAttribute("disabled", "disabled");
  try {
    const result = await apiFetch(`/api/projects/${appState.currentProjectId}/runs/cleanup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        run_ids: pendingCleanupRunIds,
        confirm: true,
      }),
    });
    const deletedCount = Array.isArray(result.deleted) ? result.deleted.length : 0;
    const skippedCount = Array.isArray(result.skipped) ? result.skipped.length : 0;
    showToast(`已清理 ${deletedCount} 個測試 Run${skippedCount ? `，略過 ${skippedCount} 個` : ""}。`);
    selectedCleanupRunIds = new Set();
    hideRunCleanupConfirmation();
    await loadAutoLabelModels(true);
    await loadWeightManagerModels();
    await loadRunCleanupCandidates();
    renderWeightManager();
  } catch (err) {
    showToast(err.message || "清理測試 Run 失敗。");
  } finally {
    confirmButton?.removeAttribute("disabled");
  }
}

async function loadWeightManagerModels() {
  if (!appState.currentProjectId) {
    weightManagerModels = [];
    return;
  }
  try {
    const models = await apiFetch(`/api/projects/${appState.currentProjectId}/models?scope=all`);
    weightManagerModels = Array.isArray(models) ? models : [];
  } catch (err) {
    weightManagerModels = [];
    showToast(err.message || "Failed to load model weights.");
  }
}

async function uploadAutoLabelSourceFiles(files) {
  if (!appState.currentProjectId) {
    showToast(t("autoLabel.startReason.noProject"));
    return;
  }

  const allFiles = [...(files || [])];
  if (!allFiles.length) {
    showToast(t("autoLabel.toast.noFiles"));
    return;
  }

  const dropZone = qs("#auto-source-drop-zone");
  const progressPanel = ensureAutoProgressPanel("auto-source-upload-progress", dropZone);
  updateAutoProgress(progressPanel, t("autoLabel.progress.filtering"), 0, t("autoLabel.progress.analyzing"));

  const classified = classifyAutoLabelSourceFiles(allFiles);
  const imageFiles = classified.images;
  const zipFiles = classified.zips;
  const rejected = classified.rejected.length;
  if (rejected > 0) showToast(t("autoLabel.toast.filteredSource", { count: rejected }));

  if (!imageFiles.length && !zipFiles.length) {
    progressPanel?.remove();
    showToast(t("autoLabel.toast.noImageOrZip"));
    return;
  }

  let importedImages = 0;
  let duplicateSameHash = 0;
  let renamedCount = 0;
  try {
    for (let idx = 0; idx < zipFiles.length; idx += 1) {
      const file = zipFiles[idx];
      updateAutoProgress(progressPanel, t("autoLabel.progress.importingZip"), Math.round((idx / Math.max(1, zipFiles.length)) * 100), t("autoLabel.progress.processingZip", { name: file.name }));
      const formData = new FormData();
      formData.append("file", file, file.name);
      const data = await apiFetch(`/api/projects/${appState.currentProjectId}/import-zip`, { method: "POST", body: formData });
      importedImages += Number(data.imported_images || 0);
    }

    const batchSize = 50;
    const totalBatches = Math.ceil(imageFiles.length / batchSize);
    for (let i = 0; i < imageFiles.length; i += batchSize) {
      const batchIndex = Math.floor(i / batchSize) + 1;
      const batch = imageFiles.slice(i, i + batchSize);
      updateAutoProgress(progressPanel, t("autoLabel.progress.uploadingImages"), Math.round((i / Math.max(1, imageFiles.length)) * 100), t("autoLabel.progress.uploadingBatch", { index: batchIndex, total: totalBatches, count: batch.length }));
      const formData = new FormData();
      batch.forEach((file) => formData.append("files", file, file.name));
      const data = await apiFetch(`/api/projects/${appState.currentProjectId}/upload-images`, { method: "POST", body: formData });
      importedImages += Number(data.uploaded_count || 0);
      duplicateSameHash += Number(data.duplicate_same_hash || 0);
      renamedCount += Number(data.renamed_same_name_diff_hash || 0);
    }

    updateAutoProgress(progressPanel, t("autoLabel.progress.syncing"), 95, t("autoLabel.progress.syncingDetail"));
    try { await apiFetch(`/api/projects/${appState.currentProjectId}/labelme/sync`, { method: "POST" }); } catch (err) { console.warn("Auto-label source sync failed", err); }
    updateAutoProgress(progressPanel, t("autoLabel.progress.completed"), 100, t("autoLabel.progress.importSummary", { imported: importedImages, duplicates: duplicateSameHash, renamed: renamedCount }));
    eventBus.emit("refresh-project");
  } catch (err) {
    showToast(t("autoLabel.toast.importFailed", { message: err.message }));
    updateAutoProgress(progressPanel, t("autoLabel.progress.failed"), 100, `Error: ${err.message}`);
  } finally {
    setTimeout(() => progressPanel?.remove(), 5000);
  }
}

async function loadAutoLabelStatus(status = null) {
  if (!status?.hasProject || !appState.currentProjectId) {
    autoLabelJobs = [];
    selectedAutoReviewItem = null;
    loadedAutoLabelStatusProjectId = null;
    renderAutoLabelStats(status);
    renderAutoLabelJobHistory();
    renderAutoLabelReviewQueue();
    return;
  }
  if (loadingAutoLabelStatus || loadedAutoLabelStatusProjectId === appState.currentProjectId) {
    return;
  }
  loadingAutoLabelStatus = true;
  try {
    const payload = await apiFetch(`/api/projects/${appState.currentProjectId}/auto-labeling/status`, { suppressToast: true });
    autoLabelJobs = Array.isArray(payload.jobs) ? payload.jobs : [];
    loadedAutoLabelStatusProjectId = appState.currentProjectId;
  } catch (err) {
    autoLabelJobs = [];
    loadedAutoLabelStatusProjectId = null;
  } finally {
    loadingAutoLabelStatus = false;
  }
  renderAutoLabelStats(status);
  renderAutoLabelJobHistory();
  renderAutoLabelReviewQueue();
}

async function createAutoLabelJob() {
  if (!appState.currentProjectId) return showToast(t("autoLabel.startReason.noProject"));
  if (!selectedAutoLabelModelId) return showToast(t("autoLabel.startReason.noModel"));
  const button = qs("#btn-start-auto-label");
  const draftRules = readAutoDraftRules();
  button?.setAttribute("disabled", "disabled");
  try {
    const payload = await apiFetch(`/api/projects/${appState.currentProjectId}/auto-labeling/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model_id: selectedAutoLabelModelId,
        source: selectedAutoSource,
        mode: "draft",
        ...draftRules,
      }),
    });
    showToast(t("autoLabel.toast.jobCreated", { job: payload.job_id || "--" }));
    loadedAutoLabelStatusProjectId = null;
    await loadAutoLabelStatus({ hasProject: true });
    renderAutoLabelReviewQueue();
  } catch (err) {
    showToast(t("autoLabel.toast.jobFailed", { message: err.message }));
  } finally {
    button?.removeAttribute("disabled");
    renderStartReason();
  }
}

function readAutoDraftRules() {
  const parseNumber = (selector, fallback) => {
    const value = Number(qs(selector)?.value);
    return Number.isFinite(value) ? value : fallback;
  };
  const classFilter = String(qs("#auto-class-filter")?.value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return {
    conf: Math.max(0.01, Math.min(1, parseNumber("#auto-confidence", 0.35))),
    iou: Math.max(0.01, Math.min(1, parseNumber("#auto-iou", 0.5))),
    max_det: Math.max(1, Math.min(300, Math.round(parseNumber("#auto-max-detections", 20)))),
    min_mask_area: Math.max(0, Math.round(parseNumber("#auto-min-mask-area", 400))),
    output_mode: qs("#auto-output-mode")?.value || "mask_polygon",
    class_filter: classFilter.length ? classFilter : null,
  };
}

function ensureAutoProgressPanel(id, anchor) {
  let panel = qs(`#${id}`);
  if (!panel) {
    panel = document.createElement("div");
    panel.id = id;
    panel.className = "ingest-progress-container";
    anchor?.parentNode?.insertBefore(panel, anchor.nextSibling);
  }
  return panel;
}

function updateAutoProgress(panel, statusText, percent, detailsText) {
  if (!panel) return;
  const safePercent = Math.max(0, Math.min(100, Number(percent) || 0));
  panel.innerHTML = `
    <div class="ingest-progress-header"><span class="ingest-progress-status">${escapeHtml(statusText)}</span><span class="ingest-progress-percent">${safePercent}%</span></div>
    <div class="ingest-progress-bar-bg"><div class="ingest-progress-bar-fill" style="width: ${safePercent}%"></div></div>
    <div class="ingest-progress-details">${escapeHtml(detailsText)}</div>
  `;
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
  setText("#auto-stat-drafts", appState.currentProjectId ? String(autoLabelJobs.length) : "0");
  setText("#auto-stat-review", appState.currentProjectId ? String(autoLabelJobs.filter((job) => String(job.status || "").toLowerCase() === "draft").length) : "0");
}

function renderStartReason(status = null) {
  const reason = qs("#auto-start-reason");
  const button = qs("#btn-start-auto-label");
  const hasProject = Boolean(status?.hasProject ?? appState.currentProjectId);
  const hasDataset = Boolean(status?.hasDataset ?? (appState.currentProject?.images || []).length);
  const hasModel = Boolean(selectedAutoLabelModelId || (appState.models || []).length);
  const canStart = hasProject && hasDataset && hasModel;
  if (button) {
    button.disabled = !canStart;
    button.classList.toggle("btn-disabled", !canStart);
  }
  if (!reason) return;
  if (!hasProject) {
    reason.textContent = t("autoLabel.startReason.noProject");
    return;
  }
  if (!hasDataset) {
    reason.textContent = t("autoLabel.startReason.noDataset");
    return;
  }
  if (!hasModel) {
    reason.textContent = t("autoLabel.startReason.noModel");
    return;
  }
  reason.textContent = t("autoLabel.startReason.ready");
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
      renderStartReason(status);
    });
  });
}

function renderAutoLabelJobHistory() {
  const body = qs("#auto-job-history-body");
  if (!body) return;
  if (!autoLabelJobs.length) {
    setHTML("#auto-job-history-body", `<tr><td colspan="5">${escapeHtml(t("autoLabel.emptyJobsShort"))}</td></tr>`);
    return;
  }
  setHTML("#auto-job-history-body", autoLabelJobs.map((job) => `
    <tr>
      <td><code>${escapeHtml(job.job_id || "--")}</code></td>
      <td>${escapeHtml(job.source || "--")}</td>
      <td><code>${escapeHtml(job.model_id || "--")}</code></td>
      <td><span class="status-badge success">${escapeHtml(job.status || "draft")}</span></td>
      <td>${Number(job.draft_count || job.drafts || 0)}</td>
    </tr>
  `).join(""));
}

function getAutoLabelReviewItems() {
  return (autoLabelJobs || []).flatMap((job) => {
    const items = Array.isArray(job.items) ? job.items : [];
    return items.map((item) => ({ ...item, job_id: job.job_id || item.job_id || "" }));
  });
}

function renderAutoLabelReviewQueue() {
  const body = qs("#auto-review-queue-body");
  if (!body) return;

  const items = getAutoLabelReviewItems();
  setText("#auto-review-queue-count", String(items.length));
  if (!items.length) {
    setHTML("#auto-review-queue-body", `<tr><td colspan="3">${escapeHtml(t("autoLabel.emptyQueueShort"))}</td></tr>`);
    selectedAutoReviewItem = null;
    clearAutoLabelPreview();
    updateAutoReviewToolbar();
    return;
  }
  const selectedKey = selectedAutoReviewItem ? autoReviewItemKey(selectedAutoReviewItem) : "";
  const selectedItem = items.find((item) => autoReviewItemKey(item) === selectedKey) || items[0];
  selectedAutoReviewItem = selectedItem;

  setHTML("#auto-review-queue-body", items.map((item, index) => {
    const summary = item.inference_summary || {};
    const confidence = summary.average_confidence ?? item.confidence ?? "";
    const label = firstDetectedClass(summary) || "--";
    const reviewStatus = item.review_status || (item.shape_count ? "review" : "empty");
    const statusClass = item.review_status ? "success" : (item.shape_count ? "warning" : "danger");
    const selected = autoReviewItemKey(item) === autoReviewItemKey(selectedItem) ? "selected" : "";
    return `
      <tr class="${selected}">
        <td>
          <button type="button" class="btn-small secondary" data-auto-review-preview="${index}">${escapeHtml(item.filename || "--")}</button>
          <div class="form-hint">${confidence === "" ? "--" : Number(confidence).toFixed(2)}</div>
        </td>
        <td>${escapeHtml(label)}</td>
        <td><span class="status-badge ${statusClass}">${escapeHtml(reviewStatus)}</span></td>
      </tr>
    `;
  }).join(""));

  qsa("[data-auto-review-preview]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = items[Number(button.dataset.autoReviewPreview || 0)];
      if (item) showAutoLabelPreview(item);
    });
  });

  showAutoLabelPreview(selectedItem);
}

function showAutoLabelPreview(item) {
  const original = qs("#auto-review-original");
  const overlay = qs("#auto-review-overlay");
  if (!original || !overlay) return;
  selectedAutoReviewItem = item || null;
  updateAutoReviewToolbar();

  const filename = item?.filename || "";
  const originalUrl = appState.currentProjectId && filename
    ? `/api/projects/${encodeURIComponent(appState.currentProjectId)}/images/${encodeURIComponent(filename)}`
    : "";
  const previewUrl = item?.preview_url || "";

  original.classList.remove("preview-placeholder");
  overlay.classList.remove("preview-placeholder");
  original.innerHTML = originalUrl
    ? `<img src="${escapeHtml(originalUrl)}" alt="${escapeHtml(filename)}">`
    : escapeHtml(t("autoLabel.noSourceImage"));
  overlay.innerHTML = previewUrl
    ? `<img src="${escapeHtml(previewUrl)}" alt="${escapeHtml(filename)} draft overlay">`
    : escapeHtml(t("autoLabel.noOverlayPreview"));

  const summary = item?.inference_summary || {};
  setText("#auto-review-class", firstDetectedClass(summary) || "--");
  setText("#auto-review-confidence", summary.average_confidence === undefined ? "--" : Number(summary.average_confidence).toFixed(2));
  setText("#auto-review-issue", item?.review_status || (item?.shape_count ? t("autoLabel.reviewStatus.needsReview") : t("autoLabel.reviewStatus.emptyDraft")));
  setText("#auto-review-state", item?.draft_labelme_url ? t("autoLabel.reviewStatus.selected", { filename: item?.filename || "--" }) : t("autoLabel.reviewStatus.draftJsonMissing"));
  renderAutoShapeTable(item);
  renderAutoReviewTaskInfo(item);
  renderAutoReviewPosition();
}

function clearAutoLabelPreview() {
  const original = qs("#auto-review-original");
  const overlay = qs("#auto-review-overlay");
  if (original) {
    original.classList.add("preview-placeholder");
    original.textContent = t("autoLabel.noDraft");
  }
  if (overlay) {
    overlay.classList.add("preview-placeholder");
    overlay.textContent = t("autoLabel.overlayHelp");
  }
  setText("#auto-review-class", "--");
  setText("#auto-review-confidence", "--");
  setText("#auto-review-issue", "--");
  setText("#auto-review-state", "--");
  setHTML("#auto-shape-table-body", `<tr><td colspan="5">${escapeHtml(t("autoLabel.noSelectedDraft"))}</td></tr>`);
  renderAutoReviewTaskInfo(null);
  renderAutoReviewPosition();
  updateAutoReviewToolbar();
}

function renderAutoShapeTable(item) {
  const predictions = item?.inference_summary?.predictions || item?.predictions || [];
  const shapeCount = Number(item?.shape_count || 0);
  if (!Array.isArray(predictions) || !predictions.length) {
    setHTML("#auto-shape-table-body", `<tr><td colspan="5">${escapeHtml(shapeCount ? t("autoLabel.shapeCount", { count: shapeCount }) : t("autoLabel.noShapeDetails"))}</td></tr>`);
    return;
  }
  setHTML("#auto-shape-table-body", predictions.slice(0, 12).map((row, index) => {
    const label = row.class_name || row.label || row.name || row.class_id || "--";
    const confidence = row.confidence ?? row.score ?? "";
    const shapeType = row.type || (row.polygon ? "polygon" : row.bbox ? "bbox" : "--");
    const issue = row.issue || row.warning || "--";
    return `
      <tr>
        <td>${index + 1}</td>
        <td>${escapeHtml(label)}</td>
        <td>${escapeHtml(shapeType)}</td>
        <td>${confidence === "" ? "--" : Number(confidence).toFixed(2)}</td>
        <td>${escapeHtml(issue)}</td>
      </tr>
    `;
  }).join(""));
}

function renderAutoReviewTaskInfo(item) {
  const job = item ? (autoLabelJobs || []).find((candidate) => candidate.job_id === item.job_id) : null;
  setText("#auto-review-job-id", job?.job_id || item?.job_id || "--");
  setText("#auto-review-job-status", job?.status || "--");
  setText("#auto-review-source", job?.source || "--");
  setText("#auto-review-model", job?.model_id || "--");
  setText("#auto-review-draft-path", job?.draft_dir || "--");
}

async function reviewSelectedAutoLabelItem(action, options = {}) {
  if (!appState.currentProjectId || !selectedAutoReviewItem) {
    showToast(t("autoLabel.toast.selectDraftFirst"));
    return;
  }
  const previousItems = getAutoLabelReviewItems();
  const previousIndex = getSelectedReviewIndex(previousItems);
  const jobId = selectedAutoReviewItem.job_id || "";
  const filename = selectedAutoReviewItem.filename || "";
  if (!jobId || !filename) {
    showToast(t("autoLabel.toast.missingDraftIdentity"));
    return;
  }

  setAutoReviewToolbarDisabled(true);
  try {
    const result = await apiFetch(`/api/projects/${appState.currentProjectId}/auto-labeling/jobs/${encodeURIComponent(jobId)}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename, action }),
    });
    showToast(t("autoLabel.toast.reviewUpdated", { filename, status: result.review_status || action }));
    loadedAutoLabelStatusProjectId = null;
    await loadAutoLabelStatus({ hasProject: true });
    if (options.moveNext) {
      const refreshedItems = getAutoLabelReviewItems();
      const nextIndex = Math.min(Math.max(previousIndex, 0) + 1, Math.max(refreshedItems.length - 1, 0));
      if (refreshedItems[nextIndex]) {
        selectedAutoReviewItem = refreshedItems[nextIndex];
      }
      renderAutoLabelReviewQueue();
    }
    eventBus.emit("refresh-project");
  } catch (err) {
    showToast(t("autoLabel.toast.reviewFailed", { message: err.message }));
  } finally {
    updateAutoReviewToolbar();
  }
}

function editSelectedAutoLabelItem() {
  if (!selectedAutoReviewItem?.draft_labelme_url) {
    showToast(t("autoLabel.toast.noDraftJson"));
    return;
  }
  openAutoLabelReviewUrl(selectedAutoReviewItem.draft_labelme_url);
}

function openAutoLabelReviewUrl(url) {
  if (!url) return;
  const opened = window.open(new URL(url, window.location.origin).toString(), "_blank");
  if (opened) opened.opener = null;
}

function updateAutoReviewToolbar() {
  const hasItem = Boolean(selectedAutoReviewItem);
  const hasDraftJson = Boolean(selectedAutoReviewItem?.draft_labelme_url);
  setAutoReviewToolbarDisabled(!hasItem);
  const editButton = qs("#btn-auto-review-edit");
  if (editButton) {
    editButton.disabled = !hasDraftJson;
    editButton.title = hasDraftJson
      ? t("autoLabel.editDraftTitle")
      : t("autoLabel.selectDraftJsonTitle");
  }
  updateAutoReviewNavigation();
}

function setAutoReviewToolbarDisabled(disabled) {
  [
    "#btn-auto-review-accept",
    "#btn-auto-review-reject",
    "#btn-auto-review-accept-next",
    "#btn-auto-review-reject-next",
    "#btn-auto-review-skip",
    "#btn-auto-review-hard-case",
    "#btn-auto-review-edit",
  ].forEach((selector) => {
    const button = qs(selector);
    if (button) button.disabled = disabled;
  });
}

function navigateAutoReviewItem(offset) {
  const items = getAutoLabelReviewItems();
  if (!items.length) return;
  const currentIndex = getSelectedReviewIndex(items);
  const fallbackIndex = currentIndex < 0 ? 0 : currentIndex;
  const nextIndex = Math.max(0, Math.min(items.length - 1, fallbackIndex + offset));
  selectedAutoReviewItem = items[nextIndex];
  renderAutoLabelReviewQueue();
}

function getSelectedReviewIndex(items = getAutoLabelReviewItems()) {
  const selectedKey = selectedAutoReviewItem ? autoReviewItemKey(selectedAutoReviewItem) : "";
  return items.findIndex((item) => autoReviewItemKey(item) === selectedKey);
}

function renderAutoReviewPosition() {
  const items = getAutoLabelReviewItems();
  const currentIndex = getSelectedReviewIndex(items);
  const label = items.length && currentIndex >= 0 ? `${currentIndex + 1} / ${items.length}` : `0 / ${items.length}`;
  setText("#auto-review-position", label);
  updateAutoReviewNavigation();
}

function updateAutoReviewNavigation() {
  const items = getAutoLabelReviewItems();
  const currentIndex = getSelectedReviewIndex(items);
  const prevButton = qs("#btn-auto-review-prev");
  const nextButton = qs("#btn-auto-review-next");
  if (prevButton) prevButton.disabled = currentIndex <= 0;
  if (nextButton) nextButton.disabled = currentIndex < 0 || currentIndex >= items.length - 1;
}

function autoReviewItemKey(item = {}) {
  return `${item.job_id || ""}/${item.filename || ""}`;
}

function firstDetectedClass(summary = {}) {
  const classes = summary.classes || summary.detected_classes || [];
  if (Array.isArray(classes) && classes.length) {
    const first = classes[0];
    if (typeof first === "string") return first;
    return first?.name || first?.class_name || String(first?.class_id ?? "");
  }
  return summary.class_name || "";
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
