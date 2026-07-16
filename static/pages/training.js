import { eventBus } from "../event_bus.js";
import { appState, getProjectStatus, t } from "../state.js";
import { apiFetch } from "../api.js";
import { qs, qsa, setText, setHTML, escapeHtml } from "../utils.js";
import { initTrainingModeSidebar } from "./training_modes.js";

// Training UI helper
let metricsCharts = [];
let currentChartData = null; // Training UI helper
let activeChartTab = "primary"; // Training UI helper
const activeGlobalTrainingJobs = new Set();
const trainingHudStartTimes = new Map();
let lastRenderedMetricRunId = "";
let lastRenderedMetricEpochCount = -1;
let trainingHudTickTimer = null;
let trainingModelCatalog = [];
let loadedTrainingModelCatalogProjectId = null;
let trainingStatusPollTimer = null;
let trainingStatusPollInFlight = false;
let metricLoadRequestId = 0;
let metricLoadInFlightRunId = "";

const ACTIVE_TRAINING_STATUSES = new Set(["training", "stopping"]);
const TERMINAL_TRAINING_STATUSES = new Set(["completed", "failed", "stopped"]);

function isSequenceTrainingRecord(record = {}) {
  const architecture = String(record.architecture || "").toLowerCase();
  const backend = String(record.backend || "").toLowerCase();
  const taskType = String(record.task_type || record.taskType || "").toLowerCase();
  return architecture === "rnn" ||
    ["pytorch_lstm", "sklearn_xgboost"].includes(backend) ||
    taskType.includes("sequence");
}

function sequenceBackendLabel(record = {}) {
  const backend = String(record.backend || "").toLowerCase();
  if (backend === "sklearn_xgboost") return "XGBoost";
  if (backend === "pytorch_lstm") return "RNN";
  return "Sequence";
}

function setMetricsDashboardActive(active) {
  qs("#training-metrics-empty")?.classList.toggle("hidden", active);
  qs("#training-metrics-active")?.classList.toggle("hidden", !active);
}

export function initTraining() {
  initTrainingModeSidebar();
  loadTrainingModelCatalog(true);

  qs("#tab-config-simple")?.addEventListener("click", () => {
    qs("#tab-config-simple")?.classList.add("active");
    qs("#tab-config-simple")?.setAttribute("aria-selected", "true");
    qs("#tab-config-advanced")?.classList.remove("active");
    qs("#tab-config-advanced")?.setAttribute("aria-selected", "false");
    qs("#config-advanced-fields")?.classList.add("hidden");
  });
  qs("#tab-config-advanced")?.addEventListener("click", () => {
    qs("#tab-config-simple")?.classList.remove("active");
    qs("#tab-config-simple")?.setAttribute("aria-selected", "false");
    qs("#tab-config-advanced")?.classList.add("active");
    qs("#tab-config-advanced")?.setAttribute("aria-selected", "true");
    qs("#config-advanced-fields")?.classList.remove("hidden");
  });

  ["#train-model", "#train-batch", "#train-imgsz", "#train-device"].forEach((selector) => {
    qs(selector)?.addEventListener("change", () => renderTrainingMonitor());
  });
  qs("#train-profile")?.addEventListener("change", (event) => {
    applyTrainingProfile(event.target.value);
    renderTrainingProfileGuide();
    renderTrainingMonitor();
  });
  renderTrainingProfileGuide();
  qs("#btn-training-open-model-hub")?.addEventListener("click", () => {
    openModelImportModal();
  });
  eventBus.on("open-model-import", (options = {}) => openModelImportModal(options));
  qs("#btn-close-model-import-modal")?.addEventListener("click", closeModelImportModal);
  qs("#btn-cancel-model-import")?.addEventListener("click", closeModelImportModal);
  qs("#model-import-modal")?.addEventListener("click", (event) => {
    if (event.target.id === "model-import-modal") closeModelImportModal();
  });
  qs("#form-import-model")?.addEventListener("submit", importYoloModelFromModal);
  qs("#model-import-type")?.addEventListener("change", updateModelImportTypeUi);
  qs("#model-import-result")?.addEventListener("click", handleModelImportApprovalClick);
  initModelImportDropZone();

  qs("#btn-start-train")?.addEventListener("click", async () => {
    const status = getProjectStatus(appState.currentProject);
    const blockers = getTrainingBlockers(status);
    const modelSelect = qs("#train-model");
    const modelName = modelSelect?.value || "";
    const selectedOption = modelSelect?.selectedOptions?.[0];
    const taskType = String(status.taskType || "").toLowerCase();
    const isSegTask = taskType.includes("segmentation") || taskType.includes("seg");
    const selectedTaskFamily = selectedOption?.dataset?.taskFamily || "";
    const isSegModel = selectedTaskFamily === "segmentation" || modelName.includes("-seg");

    if (isSegTask && !isSegModel) {
      eventBus.emit("toast", t("training.toast.segModel"));
      return;
    }

    if (blockers.length > 0) {
      eventBus.emit("toast", t("training.toast.blocked"));
      return;
    }

    try {
      const configData = {
        model: modelName,
        epochs: Number(qs("#train-epochs")?.value || 50),
        batch_size: Number(qs("#train-batch")?.value || 8),
        imgsz: Number(qs("#train-imgsz")?.value || 640),
        lr0: Number(qs("#train-lr0")?.value || 0.01),
        device: qs("#train-device")?.value || "gpu",
        patience: Number(qs("#train-patience")?.value || 20),
        workers: Number(qs("#train-workers")?.value || 4),
        cache: qs("#train-cache")?.checked || false,
        amp: qs("#train-amp")?.checked || false,
        seed: Number(qs("#train-seed")?.value || 42),
        save_period: Number(qs("#train-save-period")?.value || 5),
        close_mosaic: Number(qs("#train-close-mosaic")?.value || 10),
        optimizer: qs("#train-optimizer")?.value || "auto"
      };

      const runIdInput = qs("#train-run-id-input")?.value?.trim();
      if (runIdInput) configData.run_id = runIdInput;

      const startPayload = await apiFetch(`/api/projects/${appState.currentProjectId}/train/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(configData)
      });

      appState.trainingStatus = {
        status: "training",
        epoch: 0,
        total_epochs: configData.epochs,
        metrics: [],
        error: "",
        run_id: startPayload?.run_id || configData.run_id || "",
        started_at: new Date().toISOString(),
        architecture: taskType.includes("sequence") ? "rnn" : "cnn",
        backend: selectedOption?.dataset?.backend || "ultralytics_yolo"
      };
      renderTrainingMonitor();
      eventBus.emit("toast", t("training.toast.started"));
      startMonitorWebSocket();
      eventBus.emit("refresh-project");
    } catch (err) {
      eventBus.emit("toast", t("training.toast.startFailed", { message: err.message }));
    }
  });

  qs("#btn-stop-train")?.addEventListener("click", async () => {
    try {
      await apiFetch(`/api/projects/${appState.currentProjectId}/train/stop`, { method: "POST" });
      eventBus.emit("toast", t("training.toast.stopSent"));
    } catch (err) {
      eventBus.emit("toast", t("training.toast.stopFailed", { message: err.message }));
    }
  });

  qs("#btn-abort-train")?.addEventListener("click", async () => {
    try {
      const previous = appState.trainingStatus || {};
      const runId = previous.run_id || appState.currentProjectId || "training";
      await apiFetch(`/api/projects/${appState.currentProjectId}/train/abort`, { method: "POST" });
      appState.trainingStatus = {
        ...previous,
        status: "stopped",
        completed_at: new Date().toISOString(),
        error: previous.error || "User aborted training."
      };
      activeGlobalTrainingJobs.delete(`training-${runId}`);
      trainingHudStartTimes.delete(`training-${runId}`);
      eventBus.emit("progress:hide", { jobId: `training-${runId}` });
      stopTrainingHudTickerIfIdle();
      renderTrainingMonitor();
      eventBus.emit("toast", t("training.toast.abortSent"));
    } catch (err) {
      eventBus.emit("toast", t("training.toast.abortFailed", { message: err.message }));
    }
  });

  qs("#chart-show-raw")?.addEventListener("change", updateChartVisualization);
  qs("#chart-show-smooth")?.addEventListener("change", updateChartVisualization);
  qs("#chart-ema-alpha")?.addEventListener("input", (e) => {
    setText("#chart-ema-alpha-val", e.target.value);
    updateChartVisualization();
  });

  qsa("#metrics-chart-tabs .tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      qsa("#metrics-chart-tabs .tab-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      activeChartTab = btn.dataset.chartTab;

      if (activeChartTab === "report") {
        qs("#chart-drawing-container")?.classList.add("hidden");
        qs("#chart-report-container")?.classList.remove("hidden");
        updateReportTabImage();
      } else {
        qs("#chart-drawing-container")?.classList.remove("hidden");
        qs("#chart-report-container")?.classList.add("hidden");
        updateChartVisualization();
      }
    });
  });

  qsa("#log-tabs-nav button").forEach((btn) => {
    btn.addEventListener("click", () => {
      qsa("#log-tabs-nav button").forEach((b) => {
        b.classList.remove("btn-primary");
        b.classList.add("btn-secondary");
      });
      btn.classList.remove("btn-secondary");
      btn.classList.add("btn-primary");

      const tab = btn.dataset.logTab;
      if (tab === "epoch") {
        qs("#log-epoch-container")?.classList.remove("hidden");
        qs("#log-event-container")?.classList.add("hidden");
      } else {
        qs("#log-epoch-container")?.classList.add("hidden");
        qs("#log-event-container")?.classList.remove("hidden");
      }
    });
  });

  eventBus.on("check-training-websocket", () => {
    if (appState.trainingStatus?.status === "training") startMonitorWebSocket();
  });
  eventBus.on("start-training-monitor", () => startMonitorWebSocket());
  eventBus.on("language-changed", () => {
    renderTrainingProfileGuide();
    renderTrainingMonitor();
  });
  eventBus.on("state-changed", () => loadTrainingModelCatalog());
}

const TRAINING_PROFILES = {
  balanced: { epochs: 50, batch: 8, imgsz: 640, patience: 20 },
  quick: { epochs: 5, batch: 4, imgsz: 512, patience: 5 },
  accuracy: { epochs: 100, batch: 4, imgsz: 768, patience: 30 },
};

function applyTrainingProfile(profile) {
  const preset = TRAINING_PROFILES[profile];
  if (!preset) return;
  Object.entries({
    "#train-epochs": preset.epochs,
    "#train-batch": preset.batch,
    "#train-imgsz": preset.imgsz,
    "#train-patience": preset.patience,
  }).forEach(([selector, value]) => {
    const field = qs(selector);
    if (!field) return;
    field.value = String(value);
    field.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

function renderTrainingProfileGuide() {
  const host = qs("#training-profile-guide");
  if (!host) return;
  const profile = qs("#train-profile")?.value || "balanced";
  const keys = {
    balanced: ["fa-scale-balanced", "training.profileBalanced", "training.profileBalancedUse", "training.profileBalancedBenefit", "training.profileBalancedCaution", "50 / 8 / 640 / 20"],
    quick: ["fa-bolt", "training.profileQuick", "training.profileQuickUse", "training.profileQuickBenefit", "training.profileQuickCaution", "5 / 4 / 512 / 5"],
    accuracy: ["fa-bullseye", "training.profileAccuracy", "training.profileAccuracyUse", "training.profileAccuracyBenefit", "training.profileAccuracyCaution", "100 / 4 / 768 / 30"],
    custom: ["fa-sliders", "training.profileCustom", "training.profileCustomUse", "training.profileCustomBenefit", "training.profileCustomCaution", t("training.profileCustomValues")],
  };
  const [icon, title, use, benefit, caution, values] = keys[profile] || keys.balanced;
  host.innerHTML = `
    <div class="training-profile-guide-title"><i class="fa-solid ${icon}"></i><span><strong>${escapeHtml(t(title))}</strong><small>${escapeHtml(t(use))}</small></span></div>
    <ul>
      <li><strong>${escapeHtml(t("training.profileParameters"))}</strong><span class="no-i18n">${escapeHtml(values)}</span></li>
      <li><strong>${escapeHtml(t("training.profileBenefit"))}</strong><span>${escapeHtml(t(benefit))}</span></li>
      <li><strong>${escapeHtml(t("training.profileCaution"))}</strong><span>${escapeHtml(t(caution))}</span></li>
    </ul>`;
}

async function loadTrainingModelCatalog(force = false) {
  const select = qs("#train-model");
  if (!select) return;
  if (!appState.currentProjectId) {
    loadedTrainingModelCatalogProjectId = null;
    renderFallbackTrainingModelOptions(select);
    return;
  }
  if (!force && loadedTrainingModelCatalogProjectId === appState.currentProjectId && trainingModelCatalog.length > 0) {
    return;
  }
  try {
    const response = await apiFetch(`/api/projects/${appState.currentProjectId}/models/catalog?architecture=cnn&usage=train`);
    trainingModelCatalog = Array.isArray(response.models) ? response.models : [];
    loadedTrainingModelCatalogProjectId = appState.currentProjectId;
    renderTrainingModelOptions(select, trainingModelCatalog);
  } catch (err) {
    console.warn("Failed to load model catalog", err);
    renderFallbackTrainingModelOptions(select);
  }
}

function renderFallbackTrainingModelOptions(select) {
  trainingModelCatalog = [];
  select.innerHTML = `
    <optgroup label="Built-in Models">
      <option value="yolov8n-seg.pt" data-task-family="segmentation" data-source="builtin" data-backend="ultralytics_yolo">YOLOv8n Segmentation (Recommended)</option>
      <option value="yolov8s-seg.pt" data-task-family="segmentation" data-source="builtin" data-backend="ultralytics_yolo">YOLOv8s Segmentation</option>
      <option value="yolov8m-seg.pt" data-task-family="segmentation" data-source="builtin" data-backend="ultralytics_yolo">YOLOv8m Segmentation</option>
      <option value="yolov8n.pt" data-task-family="detection" data-source="builtin" data-backend="ultralytics_yolo">YOLOv8n Detection only</option>
      <option value="yolov8s.pt" data-task-family="detection" data-source="builtin" data-backend="ultralytics_yolo">YOLOv8s Detection only</option>
    </optgroup>
  `;
}

function renderTrainingModelOptions(select, models) {
  const previous = select.value;
  const groups = [
    ["Built-in Models", models.filter((item) => item.source === "builtin")],
    ["Imported Models", models.filter((item) => item.source === "user_import")],
    ["Project Trained Models", models.filter((item) => item.source === "project_trained")]
  ];
  select.innerHTML = "";
  groups.forEach(([label, items]) => {
    const group = document.createElement("optgroup");
    group.label = label;
    if (!items.length) {
      const empty = document.createElement("option");
      empty.disabled = true;
      empty.textContent = label === "Imported Models" ? "No imported models" : "No models";
      group.appendChild(empty);
    } else {
      items.forEach((item) => {
        const option = document.createElement("option");
        option.value = item.training_value || item.weight || "";
        option.textContent = item.display_name || item.model_id;
        option.dataset.modelId = item.model_id || "";
        option.dataset.taskFamily = item.task_family || "";
        option.dataset.source = item.source || "";
        option.dataset.backend = item.backend || "";
        option.dataset.status = item.status || "";
        option.title = `${item.source || "--"} / ${item.backend || "--"} / ${item.task_family || "--"} / ${item.status || "--"}`;
        group.appendChild(option);
      });
    }
    select.appendChild(group);
  });
  if (previous && Array.from(select.options).some((option) => option.value === previous && !option.disabled)) {
    select.value = previous;
  } else {
    const firstValid = Array.from(select.options).find((option) => !option.disabled);
    if (firstValid) select.value = firstValid.value;
  }
  updateTrainingModelRegistrySkeleton(getProjectStatus(appState.currentProject));
}

function openModelImportModal(options = {}) {
  if (!appState.currentProjectId) {
    eventBus.emit("toast", "Please open a project before importing a model.");
    return;
  }
  const modal = qs("#model-import-modal");
  const status = getProjectStatus(appState.currentProject);
  const taskFamily = String(status.taskType || "").toLowerCase().includes("detect") ? "detection" : "segmentation";
  if (options.importType && qs("#model-import-type")) qs("#model-import-type").value = options.importType;
  if (qs("#model-import-task-family")) qs("#model-import-task-family").value = taskFamily;
  if (options.taskFamily && qs("#model-import-task-family")) qs("#model-import-task-family").value = options.taskFamily;
  if (qs("#model-import-result")) qs("#model-import-result").textContent = "";
  updateModelImportTypeUi();
  if (modal) modal.hidden = false;
}

function closeModelImportModal() {
  const modal = qs("#model-import-modal");
  if (modal) modal.hidden = true;
}

function initModelImportDropZone() {
  const dropZone = qs("#model-import-drop-zone");
  const fileInput = qs("#model-import-file");
  if (!dropZone || !fileInput) return;

  const openPicker = () => fileInput.click();
  dropZone.addEventListener("click", openPicker);
  dropZone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openPicker();
    }
  });
  fileInput.addEventListener("change", updateModelImportSelectedFile);

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
    const file = event.dataTransfer?.files?.[0];
    if (!file) return;
    const importType = qs("#model-import-type")?.value || "yolo_pt";
    if (!isValidModelImportFile(importType, file.name.toLowerCase())) {
      eventBus.emit("toast", getModelImportFileMessage(importType));
      return;
    }
    fileInput.files = event.dataTransfer.files;
    updateModelImportSelectedFile();
  });
}



function updateModelImportSelectedFile() {
  const file = qs("#model-import-file")?.files?.[0];
  setText("#model-import-selected-file", file ? file.name : "尚未選擇檔案");
}

async function importYoloModelFromModal(event) {
  event.preventDefault();
  if (!appState.currentProjectId) return;
  const importType = qs("#model-import-type")?.value || "yolo_pt";
  const file = qs("#model-import-file")?.files?.[0];
  const displayName = qs("#model-import-display-name")?.value?.trim() || file?.name?.replace(/\.(pt|yaml|yml|onnx|zip)$/i, "") || "";
  const taskFamily = qs("#model-import-task-family")?.value || "segmentation";
  const resultEl = qs("#model-import-result");
  const submitBtn = qs("#btn-submit-model-import");
  if (!file) {
    eventBus.emit("toast", getModelImportFileMessage(importType));
    return;
  }
  const fileName = file.name.toLowerCase();
  const validFile = isValidModelImportFile(importType, fileName);
  if (!validFile) {
    eventBus.emit("toast", getModelImportFileMessage(importType));
    return;
  }

  const formData = new FormData();
  formData.append("display_name", displayName);
  formData.append("task_family", taskFamily);
  formData.append("file", file, file.name);

  if (submitBtn) submitBtn.disabled = true;
  if (resultEl) resultEl.textContent = "Importing model...";
  try {
    const endpoint = getModelImportEndpoint(importType, appState.currentProjectId);
    const result = await apiFetch(endpoint, {
      method: "POST",
      body: formData
    });
    const modelName = result?.model?.display_name || displayName;
    eventBus.emit("toast", `Imported model: ${modelName}`);
    renderModelImportValidationResult(result, resultEl);
    if (importType === "custom_package" && result?.model?.model_id) {
      try {
        const dryRun = await requestCustomPackageDryRun(result.model.model_id);
        renderModelImportValidationResult(result, resultEl, dryRun);
      } catch (approvalErr) {
        if (resultEl) {
          resultEl.insertAdjacentHTML("beforeend", `<div class="form-error">${escapeHtml(approvalErr.message)}</div>`);
        }
      }
    }
    await loadTrainingModelCatalog(true);
    const select = qs("#train-model");
    if (select && result?.model?.trainable && result?.model?.training_value) select.value = result.model.training_value;
    renderTrainingMonitor();
  } catch (err) {
    if (resultEl) resultEl.textContent = `Import failed: ${err.message}`;
    eventBus.emit("toast", `Model import failed: ${err.message}`);
  } finally {
    if (submitBtn) submitBtn.disabled = false;
  }
}

function getModelImportEndpoint(importType, projectId) {
  if (importType === "yolo_yaml") return `/api/projects/${projectId}/models/import/yolo-yaml`;
  if (importType === "onnx") return `/api/projects/${projectId}/models/import/onnx`;
  if (importType === "rnn_package") return `/api/projects/${projectId}/models/import/rnn-package`;
  if (importType === "custom_package") return `/api/projects/${projectId}/models/import/custom-package`;
  return `/api/projects/${projectId}/models/import/yolo-pt`;
}

function isValidModelImportFile(importType, fileName) {
  if (importType === "yolo_yaml") return fileName.endsWith(".yaml") || fileName.endsWith(".yml");
  if (importType === "onnx") return fileName.endsWith(".onnx");
  if (importType === "rnn_package") return fileName.endsWith(".zip");
  if (importType === "custom_package") return fileName.endsWith(".zip");
  return fileName.endsWith(".pt");
}

function getModelImportFileMessage(importType) {
  if (importType === "yolo_yaml") return "Please select a YOLO model .yaml / .yml file.";
  if (importType === "onnx") return "Please select an ONNX .onnx file.";
  if (importType === "rnn_package") return "Please select an RNN model package .zip file.";
  if (importType === "custom_package") return "Please select a Custom Model Package .zip file.";
  return "Please select a YOLO .pt file.";
}



function updateModelImportTypeUi() {
  const importType = qs("#model-import-type")?.value || "yolo_pt";
  const input = qs("#model-import-file");
  const submit = qs("#btn-submit-model-import");
  const taskSelect = qs("#model-import-task-family");

  if (importType === "yolo_yaml") {
    if (input) input.accept = ".yaml,.yml";
    setText("#model-import-drop-title", "匯入 YOLO model architecture YAML");
    setText("#model-import-drop-help", "可接受 .yaml / .yml。這必須是 YOLO 模型架構 YAML，不是 data.yaml / dataset YAML。匯入後可作為 YOLO 訓練架構。");
    if (submit) submit.innerHTML = `<i class="fa-solid fa-file-import"></i> Import YOLO YAML`;
  } else if (importType === "onnx") {
    if (input) input.accept = ".onnx";
    setText("#model-import-drop-title", "匯入 ONNX 推論模型");
    setText("#model-import-drop-help", "可接受 .onnx。ONNX 是 inference-only，不能放入 YOLO 訓練 selector。");
    if (submit) submit.innerHTML = `<i class="fa-solid fa-file-import"></i> Import ONNX`;
  } else if (importType === "rnn_package") {
    if (input) input.accept = ".zip";
    setText("#model-import-drop-title", "匯入 RNN model package");
    setText("#model-import-drop-help", "可接受 .zip。需包含 model.pt、feature_schema、normalization_stats、sequence_config。此類目前不是 YOLO 訓練模型。");
    if (submit) submit.innerHTML = `<i class="fa-solid fa-file-import"></i> Import RNN Package`;
    if (taskSelect && !taskSelect.value.startsWith("sequence_")) taskSelect.value = "sequence_classification";
  } else if (importType === "custom_package") {
    if (input) input.accept = ".zip";
    setText("#model-import-drop-title", "匯入 Custom Model Package");
    setText("#model-import-drop-help", "可接受 .zip，必須包含 manifest.yaml、manifest.yml 或 model_manifest.json；可包含 adapter.py / train.py / preprocess.py / postprocess.py / src/*.c / src/*.cpp / weights/ / bin/。目前只做 sandbox validation，不會進入訓練。");
    if (submit) submit.innerHTML = `<i class="fa-solid fa-file-import"></i> Validate Custom Package`;
  } else {
    if (input) input.accept = ".pt";
    setText("#model-import-drop-title", "匯入 YOLO .pt 權重檔");
    setText("#model-import-drop-help", "可接受 .pt。匯入後會存到目前專案 models/imports，並可直接出現在 CNN/YOLO 訓練模型選單作為訓練起點。");
    if (submit) submit.innerHTML = `<i class="fa-solid fa-file-import"></i> Import YOLO .pt`;
  }

  if (input) input.value = "";
  updateModelImportSelectedFile();
}
function renderModelImportValidationResult(result, resultEl, dryRun = null) {
  if (!resultEl) return;
  const model = result?.model || {};
  const validation = result?.validation || {};
  const checks = Array.isArray(validation.checks) ? validation.checks : [];
  resultEl.innerHTML = `
    <div class="model-import-validation-report">
      <strong>Imported ${escapeHtml(model.display_name || "--")}</strong>
      <span>Status: <code>${escapeHtml(model.status || validation.status || "--")}</code></span>
      ${validation.execution_enabled === false ? `<span>Execution: <code>disabled</code></span>` : ""}
      <div class="model-import-checks">
        ${checks.map((check) => {
          const state = check.status || (check.skipped ? "skipped" : check.passed === false ? "failed" : "passed");
          return `
          <div class="model-import-check ${state === "failed" ? "failed" : state === "blocked" ? "skipped" : state === "skipped" ? "skipped" : "passed"}">
            <span>${escapeHtml(check.name || "--")}</span>
            <code>${escapeHtml(state)}</code>
          </div>
        `; }).join("")}
      </div>
      ${(validation.errors || []).map((err) => `<div class="form-error">${escapeHtml(err)}</div>`).join("")}
      ${(validation.warnings || []).map((warning) => `<div class="form-hint">${escapeHtml(warning)}</div>`).join("")}
      ${(validation.blocked_reasons || []).map((reason) => `<div class="form-hint">${escapeHtml(reason)}</div>`).join("")}
      ${renderCustomPackageApprovalPanel(model, dryRun)}
    </div>
  `;
}

function renderCustomPackageApprovalPanel(model, dryRun) {
  if (model?.format !== "custom_package") return "";
  const payload = dryRun?.dry_run || dryRun?.approval || null;
  if (!payload) {
    return `
      <div class="model-approval-panel">
        <div>
          <strong>Sandbox Permission Gate</strong>
          <span>Permission request is being prepared. Adapter code remains disabled.</span>
        </div>
      </div>
    `;
  }
  const gate = payload.permission_gate || {};
  const requested = Array.isArray(gate.requested_permissions) ? gate.requested_permissions : [];
  const blocked = Array.isArray(payload.blocked_reasons) ? payload.blocked_reasons : [];
  const modelId = escapeHtml(model.model_id || "");
  return `
    <div class="model-approval-panel">
      <div class="model-approval-header">
        <div>
          <strong>Sandbox Permission Gate</strong>
          <span>Status: <code>${escapeHtml(payload.status || "--")}</code></span>
        </div>
        <span class="model-approval-badge">Execution Disabled</span>
      </div>
      <div class="model-approval-summary">
        <div><span>Runtime</span><code>${escapeHtml(gate.runtime_kind || "--")}</code></div>
        <div><span>Entrypoint</span><code>${escapeHtml(gate.entrypoint || "--")}</code></div>
        <div><span>Approval</span><code>${escapeHtml(payload.approval_status || payload.decision || "pending")}</code></div>
      </div>
      <div class="model-permission-list">
        ${requested.length ? requested.map((permission) => `
          <div class="model-permission-item ${permission.risk === "high" ? "high-risk" : ""}">
            <span>${escapeHtml(permission.name || "--")}</span>
            <code>${escapeHtml(permission.risk || "unknown")}</code>
          </div>
        `).join("") : `<div class="form-hint">No optional permissions requested. Python adapter execution still requires approval.</div>`}
      </div>
      ${blocked.map((reason) => `<div class="form-hint">${escapeHtml(reason)}</div>`).join("")}
      <div class="model-approval-actions">
        <button type="button" class="btn btn-sm btn-primary" data-model-approval-action="approve" data-model-id="${modelId}">
          <i class="fa-solid fa-check"></i> Approve dry-run gate
        </button>
        <button type="button" class="btn btn-sm btn-secondary" data-model-approval-action="reject" data-model-id="${modelId}">
          <i class="fa-solid fa-ban"></i> Reject
        </button>
        <button type="button" class="btn btn-sm btn-secondary" data-model-dry-run-action="plan" data-model-id="${modelId}">
          <i class="fa-solid fa-list-check"></i> Build sandbox plan
        </button>
        <button type="button" class="btn btn-sm btn-secondary" data-model-dry-run-action="mock" data-model-id="${modelId}">
          <i class="fa-solid fa-vial"></i> Mock dry-run
        </button>
        <button type="button" class="btn btn-sm btn-secondary" data-model-dry-run-action="enablement" data-model-id="${modelId}">
          <i class="fa-solid fa-shield-halved"></i> Evaluate enablement
        </button>
        <button type="button" class="btn btn-sm btn-secondary" data-model-dry-run-action="integration" data-model-id="${modelId}">
          <i class="fa-solid fa-diagram-project"></i> Integration contract
        </button>
      </div>
      <div class="form-hint">Approval only records permission intent. Adapter import and execution remain disabled in this phase.</div>
    </div>
  `;
}

async function requestCustomPackageDryRun(modelId) {
  return apiFetch(`/api/projects/${appState.currentProjectId}/models/import/custom-package/${encodeURIComponent(modelId)}/dry-run/request`, {
    method: "POST"
  });
}

async function handleModelImportApprovalClick(event) {
  const dryRunButton = event.target.closest("[data-model-dry-run-action]");
  if (dryRunButton) {
    await handleModelImportDryRunAction(dryRunButton);
    return;
  }
  const button = event.target.closest("[data-model-approval-action]");
  if (!button || !appState.currentProjectId) return;
  const modelId = button.dataset.modelId || "";
  const decision = button.dataset.modelApprovalAction || "";
  if (!modelId || !decision) return;
  button.disabled = true;
  try {
    const formData = new FormData();
    formData.append("decision", decision);
    formData.append("approved_by", "local_user");
    formData.append("note", "Recorded from Model Import approval panel.");
    const result = await apiFetch(`/api/projects/${appState.currentProjectId}/models/import/custom-package/${encodeURIComponent(modelId)}/dry-run/approval`, {
      method: "POST",
      body: formData
    });
    eventBus.emit("toast", `Sandbox approval ${decision}: execution remains disabled.`);
    const panel = button.closest(".model-approval-panel");
    if (panel) {
      panel.insertAdjacentHTML("beforeend", `
        <div class="model-approval-decision">
          <strong>${escapeHtml(result?.approval?.status || "--")}</strong>
          <span>${escapeHtml((result?.approval?.blocked_reasons || []).join(" "))}</span>
        </div>
      `);
    }
  } catch (err) {
    eventBus.emit("toast", `Sandbox approval failed: ${err.message}`);
  } finally {
    button.disabled = false;
  }
}

async function handleModelImportDryRunAction(button) {
  if (!appState.currentProjectId) return;
  const modelId = button.dataset.modelId || "";
  const action = button.dataset.modelDryRunAction || "";
  if (!modelId || !action) return;
  button.disabled = true;
  try {
    const endpoint = action === "mock"
      ? `/api/projects/${appState.currentProjectId}/models/import/custom-package/${encodeURIComponent(modelId)}/dry-run/mock`
      : action === "enablement"
        ? `/api/projects/${appState.currentProjectId}/models/import/custom-package/${encodeURIComponent(modelId)}/enablement`
        : action === "integration"
          ? `/api/projects/${appState.currentProjectId}/models/import/custom-package/${encodeURIComponent(modelId)}/integration`
          : `/api/projects/${appState.currentProjectId}/models/import/custom-package/${encodeURIComponent(modelId)}/dry-run/plan`;
    const result = await apiFetch(endpoint, { method: "POST" });
    const payload = result?.dry_run || result?.plan || result?.enablement || result?.integration || {};
    const label = action === "mock" ? "Mock dry-run" : action === "enablement" ? "Enablement policy" : action === "integration" ? "Integration contract" : "Sandbox plan";
    eventBus.emit("toast", `${label}: ${payload.status || "completed"}`);
    const panel = button.closest(".model-approval-panel");
    if (panel) {
      panel.insertAdjacentHTML("beforeend", `
        <div class="model-approval-decision">
          <strong>${escapeHtml(payload.status || "--")}</strong>
          <span>Execution disabled. Adapter was not imported or executed.</span>
        </div>
      `);
    }
  } catch (err) {
    eventBus.emit("toast", `Sandbox ${action} failed: ${err.message}`);
  } finally {
    button.disabled = false;
  }
}

export function renderTrainingMonitor() {
  const status = getProjectStatus(appState.currentProject);
  const trainState = appState.trainingStatus || {};
  const blockers = getTrainingBlockers(status);
  const isReady = blockers.length === 0;
  const isRunning = trainState.status === "training";
  const isStopping = trainState.status === "stopping";
  const isSequenceProject = isSequenceTrainingRecord({
    architecture: appState.currentProject?.architecture,
    backend: appState.currentProject?.backend,
    task_type: appState.currentProject?.task_type
  });
  const hasMetrics = Boolean(currentChartData?.epochs?.length);

  setText("#card-ds-total", status.hasProject ? t("training.card.imageCount", { count: status.imageCount }) : "--");
  setText("#card-ds-split", status.hasProject ? t("training.card.images", { count: status.imageCount }) : t("training.card.images", { count: "--" }));
  setText("#card-ann-status", status.hasProject ? `${status.annotationRate}%` : "--");
  setText("#card-ann-detail", status.hasProject ? t("training.card.annotated", { annotated: status.annotatedCount, missing: status.unannotatedCount }) : t("training.card.annotated", { annotated: "--", missing: "--" }));
  setText("#card-split-status", status.splitComplete ? t("training.status.splitReady") : t("training.status.missing"));
  setText("#card-split-detail", status.hasProject ? t("training.card.trainValTest", { train: status.splitCounts.train, val: status.splitCounts.val, test: status.splitCounts.test }) : t("training.card.trainValTest", { train: "--", val: "--", test: "--" }));

  const hw = trainState.hardware || {};
  const gpu = hw.gpu || {};


  const startBtn = qs("#btn-start-train");
  const stopBtn = qs("#btn-stop-train");
  const abortBtn = qs("#btn-abort-train");
  const lockMsg = qs("#config-lock-msg");
  const configForm = qs("#form-training-config");
  const startBlocker = qs("#training-start-blocker");
  const operationBusy = isRunning || isStopping;
  const configFields = ["#config-simple-fields", "#config-advanced-fields"];
  const configTabs = qs(".training-config-panel .config-tabs-nav");

  if (startBtn) {
    startBtn.disabled = isRunning || isStopping;
    startBtn.dataset.requires = !isReady && !isRunning && !isStopping ? "train-ready" : "";
    startBtn.setAttribute("aria-disabled", operationBusy ? "true" : "false");
    startBtn.title = !isReady && !operationBusy ? t("training.toast.blocked") : t("training.start");
  }
  if (isRunning) {
    stopBtn?.classList.remove("hidden");
    if (stopBtn) stopBtn.disabled = false;
  } else if (isStopping) {
    stopBtn?.classList.remove("hidden");
    if (stopBtn) stopBtn.disabled = true;
  } else {
    stopBtn?.classList.add("hidden");
  }
  if (isRunning || isStopping) {
    abortBtn?.classList.remove("hidden");
    if (abortBtn) abortBtn.disabled = false;
  } else {
    abortBtn?.classList.add("hidden");
  }

  if (lockMsg) {
    lockMsg.classList.toggle("hidden", !operationBusy);
    const message = isRunning
      ? t("training.config.lockedRunning")
      : isStopping
        ? t("training.config.lockedStopping")
        : "";
    lockMsg.querySelector("span") && (lockMsg.querySelector("span").textContent = message);
  }

  if (configForm) {
    qsa("#form-training-config input, #form-training-config select").forEach((el) => {
      el.disabled = operationBusy;
    });
  }
  configFields.forEach((selector) => {
    const el = qs(selector);
    if (!el) return;
    if (selector === "#config-advanced-fields" && qs("#tab-config-advanced")?.classList.contains("active")) {
      el.classList.remove("hidden");
    } else if (selector === "#config-advanced-fields") {
      el.classList.add("hidden");
    } else {
      el.classList.remove("hidden");
    }
  });
  configTabs?.classList.remove("hidden");
  if (startBlocker) {
    startBlocker.classList.toggle("hidden", isReady);
    startBlocker.innerHTML = isReady ? "" : `<strong>${escapeHtml(t("training.startDisabled"))}</strong><ul>${blockers.map((b) => `<li>${escapeHtml(b.text)}</li>`).join("")}</ul>`;
  }

  renderReadinessGuard(status, blockers);
  updateTrainingModelRegistrySkeleton(status);
  updateTrainingRecommendation(status, gpu);

  const monitorEmpty = qs("#training-monitor-empty");
  const monitorActive = qs("#training-monitor-active");

  const showMonitor = isRunning || isStopping || TERMINAL_TRAINING_STATUSES.has(trainState.status);
  monitorEmpty?.classList.toggle("hidden", showMonitor);
  monitorActive?.classList.toggle("hidden", !showMonitor);

  const epoch = Number(trainState.epoch || 0);
  const totalEpochs = Number(trainState.total_epochs || 0);
  const displayEpoch = totalEpochs > 0 ? Math.min(epoch, totalEpochs) : epoch;
  const progressPercent = trainState.status === "completed"
    ? 100
    : totalEpochs > 0
      ? Math.min(100, Math.max(0, (epoch / totalEpochs) * 100))
      : 0;
  updateGlobalTrainingProgress(trainState, progressPercent, showMonitor);

  setText("#train-status-label", trainingStatusLabel(trainState.status));
  setText("#train-progress-text", showMonitor ? `Epoch ${displayEpoch} / ${totalEpochs || "--"}` : "--");
  renderTrainingMonitorOutcome(trainState, displayEpoch, totalEpochs);

  const lastMetrics = trainState.metrics && trainState.metrics.length ? trainState.metrics[trainState.metrics.length - 1] : {};
  const isRnnStatus = isSequenceTrainingRecord(trainState);
  updateMonitorMetricLabels(isRnnStatus, lastMetrics);
  if (isRnnStatus) {
    setText("#monitor-map50", metricValue(lastMetrics["val/accuracy"] ?? lastMetrics["val/mae"], 3));
    setText("#monitor-map50-95", metricValue(lastMetrics["val/macro_f1"] ?? lastMetrics["val/rmse"], 3));
    setText("#monitor-loss", metricValue(lastMetrics["val/loss"] ?? lastMetrics["train/loss"], 4));
  } else {
    setText("#monitor-map50", lastMetrics.map50 !== undefined ? Number(lastMetrics.map50).toFixed(3) : "--");
    setText("#monitor-map50-95", lastMetrics.map50_95 !== undefined ? Number(lastMetrics.map50_95).toFixed(3) : "--");
    setText("#monitor-loss", lastMetrics.loss !== undefined ? Number(lastMetrics.loss).toFixed(4) : "--");
  }

  if (isRunning) {
    const liveChartData = normalizeLiveTrainingMetrics(trainState);
    const liveEpochCount = liveChartData?.epochs?.length || 0;
    const liveRunId = trainState.run_id || "";
    if (liveEpochCount > 0 && (liveRunId !== lastRenderedMetricRunId || liveEpochCount !== lastRenderedMetricEpochCount)) {
      currentChartData = liveChartData;
      lastRenderedMetricRunId = liveRunId;
      lastRenderedMetricEpochCount = liveEpochCount;
      updateChartVisualization();
      renderEpochHistoryTable(currentChartData);
    }
  } else if (!isSequenceProject) {
    loadLatestRunMetricsOnce();
  }

  setMetricsDashboardActive(hasMetrics);

  if (!isSequenceProject) {
    renderRunHistoryTable();
  }
}

function updateGlobalTrainingProgress(trainState, progressPercent, showMonitor) {
  if (!showMonitor) return;
  const status = trainState.status || "idle";
  const runId = trainState.run_id || appState.currentProjectId || "training";
  const jobId = `training-${runId}`;
  const epoch = Number(trainState.epoch || 0);
  const totalEpochNumber = Number(trainState.total_epochs || 0);
  const totalEpochs = totalEpochNumber || "--";
  const displayEpoch = totalEpochNumber > 0 ? Math.min(epoch, totalEpochNumber) : epoch;
  const isPendingFirstEpoch = status === "training" && epoch <= 0;
  const elapsedSeconds = getTrainingHudElapsedSeconds(jobId, trainState);
  const pendingPhase = buildTrainingHudPendingPhase(elapsedSeconds);
  const pendingPercent = Math.min(24, Math.max(4, 4 + (elapsedSeconds * 0.45)));
  if (status === "training" || status === "stopping") {
    activeGlobalTrainingJobs.add(jobId);
    ensureTrainingHudTicker();
  }
  if (TERMINAL_TRAINING_STATUSES.has(status) && !activeGlobalTrainingJobs.has(jobId)) {
    return;
  }
  const payload = {
    jobId,
    title: status === "completed"
      ? t("training.progress.complete")
      : status === "failed"
        ? t("training.progress.failed")
        : status === "stopping"
          ? t("training.progress.stopping")
          : t("training.progress.inProgress"),
    message: isPendingFirstEpoch
      ? t(pendingPhase.key)
      : t("training.progress.running", { epoch: displayEpoch, total: totalEpochs }),
    percent: isPendingFirstEpoch ? pendingPercent : progressPercent,
    caption: status === "completed"
      ? t("training.progress.captionComplete")
      : status === "failed"
        ? t("training.progress.captionFailed")
        : t("training.progress.captionTraining"),
    indeterminate: false
  };
  if (status === "completed") {
    eventBus.emit("progress:complete", { ...payload, percent: 100 });
    activeGlobalTrainingJobs.delete(jobId);
    trainingHudStartTimes.delete(jobId);
    stopTrainingHudTickerIfIdle();
  } else if (status === "failed") {
    eventBus.emit("progress:failed", payload);
    activeGlobalTrainingJobs.delete(jobId);
    trainingHudStartTimes.delete(jobId);
    stopTrainingHudTickerIfIdle();
  } else if (status === "stopped") {
    eventBus.emit("progress:hide", { jobId });
    activeGlobalTrainingJobs.delete(jobId);
    trainingHudStartTimes.delete(jobId);
    stopTrainingHudTickerIfIdle();
  } else {
    eventBus.emit("progress:update", payload);
  }
}

function trainingStatusLabel(status = "idle") {
  const labels = {
    training: "training.progress.inProgress",
    stopping: "training.progress.stopping",
    completed: "common.completed",
    failed: "common.failed",
    stopped: "common.stopped",
    idle: "training.monitor.statusIdle"
  };
  return t(labels[status] || "training.monitor.statusIdle");
}

function renderTrainingMonitorOutcome(trainState, displayEpoch, totalEpochs) {
  const outcome = qs("#training-monitor-outcome");
  if (!outcome) return;
  const status = trainState.status || "idle";
  const isEarlyStop = status === "completed" && (
    trainState.termination_reason === "early_stopping" ||
    (displayEpoch > 0 && totalEpochs > 0 && displayEpoch < totalEpochs)
  );
  let message = "";
  let tone = "";
  if (isEarlyStop) {
    message = t("training.monitor.outcomeEarlyStop", { epoch: displayEpoch, total: totalEpochs });
    tone = "is-success";
  } else if (status === "completed") {
    message = t("training.monitor.outcomeCompleted", { epoch: displayEpoch, total: totalEpochs || displayEpoch });
    tone = "is-success";
  } else if (status === "failed") {
    message = t("training.monitor.outcomeFailed", { message: trainState.error || t("training.monitor.outcomeUnknownError") });
    tone = "is-danger";
  } else if (status === "stopped") {
    message = t("training.monitor.outcomeStopped", { epoch: displayEpoch, total: totalEpochs || "--" });
    tone = "is-warning";
  }
  outcome.classList.toggle("hidden", !message);
  outcome.classList.remove("is-success", "is-warning", "is-danger");
  if (tone) outcome.classList.add(tone);
  outcome.textContent = message;
}

function ensureTrainingHudTicker() {
  if (trainingHudTickTimer) return;
  trainingHudTickTimer = window.setInterval(() => {
    const status = appState.trainingStatus?.status;
    if (status === "training" || status === "stopping") {
      renderTrainingMonitor();
      return;
    }
    stopTrainingHudTickerIfIdle();
  }, 1000);
}

function stopTrainingHudTickerIfIdle() {
  const status = appState.trainingStatus?.status;
  if (status === "training" || status === "stopping") return;
  if (trainingHudTickTimer) {
    window.clearInterval(trainingHudTickTimer);
    trainingHudTickTimer = null;
  }
}

function getTrainingHudElapsedSeconds(jobId, trainState) {
  const startedAt = Date.parse(trainState.started_at || "");
  if (Number.isFinite(startedAt)) {
    return Math.max(0, (Date.now() - startedAt) / 1000);
  }
  if (!trainingHudStartTimes.has(jobId)) {
    trainingHudStartTimes.set(jobId, Date.now());
  }
  return Math.max(0, (Date.now() - trainingHudStartTimes.get(jobId)) / 1000);
}

function buildTrainingHudPendingPhase(elapsedSeconds) {
  if (elapsedSeconds < 8) return { key: "training.progress.phasePreparing" };
  if (elapsedSeconds < 20) return { key: "training.progress.phaseLoadingModel" };
  if (elapsedSeconds < 45) return { key: "training.progress.phaseDataLoader" };
  return { key: "training.progress.phaseFirstEpoch" };
}

export async function loadRecommendedConfig() {
  if (!appState.currentProjectId) return;
  try {
    const data = await apiFetch(`/api/projects/${appState.currentProjectId}/train/recommend`);
    
    // Training UI helper
    const modelSelect = qs("#train-model");
    if (modelSelect) {
      modelSelect.value = data.model;
    }
    
    // Training UI helper
    const fields = {
      "#train-epochs": data.epochs,
      "#train-batch": data.batch_size,
      "#train-imgsz": data.imgsz,
      "#train-lr0": data.lr0,
      "#train-patience": data.patience,
      "#train-workers": data.workers,
      "#train-seed": data.seed,
      "#train-save-period": data.save_period,
      "#train-close-mosaic": data.close_mosaic,
      "#train-optimizer": data.optimizer
    };

    for (const [selector, value] of Object.entries(fields)) {
      const el = qs(selector);
      if (el) {
        if (el.type === "checkbox") {
          el.checked = !!value;
        } else {
          el.value = value;
        }
      }
    }
    
    const ampEl = qs("#train-amp");
    if (ampEl) ampEl.checked = !!data.amp;
    const cacheEl = qs("#train-cache");
    if (cacheEl) cacheEl.checked = !!data.cache;
    
    eventBus.emit("state-changed");
  } catch (err) {
    console.error("Failed to load recommended configs", err);
  }
}

// Training UI helper
function getTrainingBlockers(status) {
  const blockers = [];
  const modelName = qs("#train-model")?.value || "";
  const taskType = String(status.taskType || "").toLowerCase();
  const isSegTask = taskType.includes("segmentation") || taskType.includes("seg");
  const isSegModel = modelName.includes("-seg");

  if (!status.hasProject) {
    blockers.push({ text: t("training.blocker.noProject"), action: t("training.action.openProject"), nav: "dashboard" });
    return blockers;
  }
  if (!status.hasDataset || status.imageCount === 0) {
    blockers.push({ text: t("training.blocker.noDataset"), action: t("training.action.importDataset"), nav: "dataset" });
  }
  if (!status.labelme?.synced) {
    blockers.push({ text: t("training.blocker.labelme"), action: t("training.action.syncLabelMe"), nav: "labelme" });
  }
  if (!status.splitComplete) {
    blockers.push({ text: t("training.blocker.split"), action: t("training.action.createSplit"), nav: "split" });
  }
  if (status.autoLabelReviewGate?.blocked) {
    const pending = status.autoLabelReviewGate.pending || 0;
    blockers.push({
      text: t("training.blocker.autoLabelReview", { pending }),
      action: t("training.action.reviewAutoLabel"),
      nav: "auto-labeling"
    });
  }
  if (isSegTask && !isSegModel) {
    blockers.push({ text: t("training.blocker.model"), action: t("training.action.chooseSegModel"), nav: null });
  }
  return blockers;
}

function renderReadinessGuard(status, blockers = getTrainingBlockers(status)) {
  const container = qs("#training-readiness-guard");
  if (!container) return;

  if (blockers.length > 0) {
    container.className = "training-readiness blocked";
    container.innerHTML = `
      <div class="training-readiness-header">
        <div><i class="fa-solid fa-triangle-exclamation"></i> ${escapeHtml(t("training.readiness.blocked"))}</div>
        <span class="summary-badge badge-danger">${escapeHtml(t("training.card.readinessBlocked", { count: blockers.length, plural: blockers.length > 1 ? "s" : "" }))}</span>
      </div>
      <p>${escapeHtml(t("training.readiness.fixBeforeStart"))}</p>
      <ul>${blockers.map((b) => `<li>${escapeHtml(b.text)}${b.nav ? ` <button type="button" class="link-button" data-nav="${b.nav}">${escapeHtml(b.action)}</button>` : ` <strong>${escapeHtml(b.action)}</strong>`}</li>`).join("")}</ul>
    `;
    container.querySelectorAll("[data-nav]").forEach((btn) => {
      btn.addEventListener("click", () => eventBus.emit("navigate", btn.dataset.nav));
    });
    return;
  }

  container.className = "training-readiness ready";
  container.innerHTML = `
    <div class="training-readiness-header">
      <div><i class="fa-solid fa-circle-check"></i> ${escapeHtml(t("training.readiness.ready"))}</div>
      <span class="summary-badge badge-success">${escapeHtml(t("training.status.ready"))}</span>
    </div>
    <p>${escapeHtml(t("training.readiness.readyDetail"))}</p>
  `;
}

function updateTrainingRecommendation(status, gpu) {
  const el = qs("#training-vram-risk-text");
  if (!el) return;
  const batch = Number(qs("#train-batch")?.value || 8);
  const imgsz = Number(qs("#train-imgsz")?.value || 640);
  const model = qs("#train-model")?.value || "";
  const vramMb = Number(gpu?.vram_total || 0);

  if (!status.hasProject) {
    el.textContent = t("training.recommend.noProject");
    return;
  }
  if (!gpu?.available) {
    el.textContent = t("training.recommend.noGpu");
    return;
  }

  let key = "training.recommend.low";
  if (vramMb && vramMb < 8000 && (batch >= 8 || imgsz >= 768)) {
    key = "training.recommend.high";
  } else if (vramMb && vramMb < 12000 && (batch >= 16 || imgsz >= 768 || model.includes("m-seg"))) {
    key = "training.recommend.medium";
  }
  el.textContent = t(key);
}

function updateTrainingModelRegistrySkeleton(status) {
  const select = qs("#train-model");
  if (!select) return;
  const modelName = select.value || "--";
  const selectedOption = select.selectedOptions?.[0];
  const taskEl = qs("#training-model-task");
  const nameEl = qs("#training-model-selected-name");
  const noteEl = qs("#training-model-compatibility");
  const taskType = String(status.taskType || "").toLowerCase();
  const isSegTask = taskType.includes("segmentation") || taskType.includes("seg");
  const selectedTaskFamily = selectedOption?.dataset?.taskFamily || "";
  const source = selectedOption?.dataset?.source || "--";
  const backend = selectedOption?.dataset?.backend || "--";
  const statusText = selectedOption?.dataset?.status || "--";
  const isSegModel = selectedTaskFamily === "segmentation" || modelName.includes("-seg");
  const modelTask = selectedTaskFamily === "segmentation" || isSegModel
    ? t("training.modelRegistry.yoloV8Seg")
    : t("training.modelRegistry.yoloV8Det");
  const compatible = !isSegTask || isSegModel;

  setText("#training-model-selected-name", selectedOption?.textContent || modelName);
  setText("#training-model-task", modelTask);
  if (nameEl) nameEl.title = [modelName, source, backend, statusText].filter(Boolean).join(" / ");
  if (taskEl) taskEl.title = [modelTask, source, backend, statusText].filter(Boolean).join(" / ");
  if (noteEl) {
    noteEl.textContent = compatible
      ? t("training.modelRegistry.compatible")
      : t("training.modelRegistry.incompatible");
    noteEl.classList.toggle("is-compatible", compatible);
    noteEl.classList.toggle("is-warning", !compatible);
  }
}

function normalizeLiveTrainingMetrics(trainState) {
  const metrics = trainState.metrics || [];
  const isRnn = isSequenceTrainingRecord(trainState);
  if (isRnn) {
    return normalizeMetricRows(metrics, {
      architecture: "rnn",
      backend: trainState.backend,
      task_type: trainState.task_type || "sequence_classification"
    });
  }

  const totalEpochs = Number(trainState.total_epochs || 0);
  const rowsByEpoch = new Map();
  metrics.forEach((metric, index) => {
    let epoch = Number(metric?.epoch ?? index + 1);
    if (!Number.isFinite(epoch) || epoch < 1) return;
    if (totalEpochs > 0) epoch = Math.min(epoch, totalEpochs);
    rowsByEpoch.set(epoch, { ...metric, epoch });
  });
  const rows = Array.from(rowsByEpoch.values()).sort((a, b) => Number(a.epoch) - Number(b.epoch));
  const wsEpochs = rows.map((m) => m.epoch);
  const wsLoss = rows.map((m) => m.loss);
  const wsMap50 = rows.map((m) => m.map50);
  const wsMap50_95 = rows.map((m) => m.map50_95);
  const wsPrecision = rows.map((m) => m.precision);
  const wsRecall = rows.map((m) => m.recall);

  return {
    architecture: "cnn",
    total_epochs: totalEpochs,
    epochs: wsEpochs,
    raw: {
      "train/box_loss": wsLoss,
      "metrics/mAP50(M)": wsMap50,
      "metrics/mAP50-95(M)": wsMap50_95,
      "metrics/precision(M)": wsPrecision,
      "metrics/recall(M)": wsRecall
    },
    smooth: {
      "train/box_loss": wsLoss,
      "metrics/mAP50(M)": wsMap50,
      "metrics/mAP50-95(M)": wsMap50_95,
      "metrics/precision(M)": wsPrecision,
      "metrics/recall(M)": wsRecall
    }
  };
}

function normalizeStoredTrainingMetrics(data) {
  if (!data) return null;
  if (Array.isArray(data.history)) {
    return normalizeMetricRows(data.history, {
      architecture: data.architecture || "rnn",
      backend: data.backend,
      task_type: data.task_type,
      primary_metric: data.primary_metric,
      best_epoch: data.best_epoch,
      best_metrics: data.best_metrics,
      dataset_summary: data.dataset_summary
    });
  }
  if (data.epochs && data.raw) {
    return {
      ...data,
      architecture: data.architecture || "cnn"
    };
  }
  return data;
}

function normalizeMetricRows(rows, meta = {}) {
  const safeRows = Array.isArray(rows) ? rows : [];
  const keys = new Set();
  safeRows.forEach((row) => {
    Object.keys(row || {}).forEach((key) => {
      if (key !== "epoch") keys.add(key);
    });
  });
  const raw = {};
  keys.forEach((key) => {
    raw[key] = safeRows.map((row) => numericOrNull(row?.[key]));
  });
  return {
    ...meta,
    epochs: safeRows.map((row, index) => row?.epoch ?? index + 1),
    raw,
    smooth: raw,
    history: safeRows
  };
}

function numericOrNull(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function metricValue(value, digits = 3) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : "--";
}

function labeledMetric(label, value, digits = 3) {
  return `<span class="metric-inline-label">${escapeHtml(label)}</span> ${metricValue(value, digits)}`;
}

function isRnnRegressionMetrics(data = {}) {
  const raw = data.raw || {};
  const taskType = String(data.task_type || "").toLowerCase();
  return taskType.includes("regression") || "val/mae" in raw || "val/rmse" in raw;
}

function updateMonitorMetricLabels(isRnn, metrics = {}) {
  const isRegression = isRnn && (metrics["val/mae"] !== undefined || metrics["val/rmse"] !== undefined);
  setText("#monitor-primary-label", isRnn ? isRegression ? "MAE" : "Accuracy" : "mAP50(M)");
  setText("#monitor-secondary-label", isRnn ? isRegression ? "RMSE" : "Macro-F1" : "mAP50-95(M)");
  setText("#monitor-loss-label", isRnn ? "Val Loss" : "Loss");
}


// Training UI helper
let lastLoadedRunId = null;
async function loadLatestRunMetricsOnce() {
  if (!appState.currentProjectId) return;
  
  // Training UI helper
  try {
    const runs = await apiFetch(`/api/projects/${appState.currentProjectId}/train/runs`);
    if (!runs || runs.length === 0) {
      currentChartData = null;
      lastRenderedMetricRunId = "";
      lastRenderedMetricEpochCount = -1;
      updateChartVisualization();
      renderEpochHistoryTable(null);
      renderArtifactList(null);
      setMetricsDashboardActive(false);
      return;
    }
    
    // Training UI helper
    const preferredRunId = appState.trainingStatus?.run_id || appState.currentProject?.current?.training_run_id || "";
    const latestRun = runs.find((run) => run.run_id === preferredRunId) || runs[0];
    if ((latestRun.run_id === lastLoadedRunId && currentChartData) || latestRun.run_id === metricLoadInFlightRunId) {
      return; // Training UI helper
    }
    
    await loadRunMetrics(latestRun.run_id);
  } catch (err) {
    console.error("loadLatestRunMetricsOnce error", err);
    setMetricsDashboardActive(false);
  }
}

// Training UI helper
async function loadRunMetrics(runId) {
  const requestId = ++metricLoadRequestId;
  metricLoadInFlightRunId = runId;
  try {
    const data = await apiFetch(`/api/projects/${appState.currentProjectId}/train/runs/${runId}/metrics`, { suppressToast: true });
    if (requestId !== metricLoadRequestId) return;
    currentChartData = normalizeStoredTrainingMetrics(data);
    lastLoadedRunId = runId;
    lastRenderedMetricRunId = runId;
    lastRenderedMetricEpochCount = currentChartData?.epochs?.length || 0;
    setMetricsDashboardActive(Boolean(currentChartData?.epochs?.length));
    
    // Training UI helper
    updateChartVisualization();
    renderEpochHistoryTable(currentChartData);
    
    // Training UI helper
    updateTrendDiagnostic(runId, requestId);
    
    // Training UI helper
    await loadRunArtifacts(runId, requestId);
  } catch (err) {
    if (requestId !== metricLoadRequestId) return;
    if (!isExpectedMissingRunMetrics(err)) {
      console.error("loadRunMetrics error", err);
    }
    currentChartData = null;
    lastRenderedMetricRunId = "";
    lastRenderedMetricEpochCount = -1;
    updateChartVisualization();
    renderEpochHistoryTable(null);
    setMetricsDashboardActive(false);
    renderArtifactList(null, runId);
  } finally {
    if (requestId === metricLoadRequestId) metricLoadInFlightRunId = "";
  }
}

// Training UI helper
async function loadRunArtifacts(runId, requestId = metricLoadRequestId) {
  try {
    const data = await apiFetch(`/api/projects/${appState.currentProjectId}/train/runs/${runId}/artifacts`, { suppressToast: true });
    if (requestId !== metricLoadRequestId) return;
    renderArtifactList(data, runId);
  } catch (err) {
    if (requestId !== metricLoadRequestId) return;
    if (!isExpectedMissingRunMetrics(err)) {
      console.error("loadRunArtifacts error", err);
    }
    renderArtifactList(null, runId);
  }
}

function isExpectedMissingRunMetrics(err) {
  const message = String(err?.message || err?.detail || "");
  return err?.status === 404 && message.includes("Metrics file not found");
}

// Training UI helper
async function updateTrendDiagnostic(runId, requestId = metricLoadRequestId) {
  try {
    const runs = await apiFetch(`/api/projects/${appState.currentProjectId}/train/runs`);
    if (requestId !== metricLoadRequestId) return;
    const run = runs.find((item) => item.run_id === runId);
    if (!run || !run.health) {
      setText("#trend-best-epoch", run?.best_epoch || "--");
      setText("#trend-platform-score", run?.platform_score !== undefined ? Number(run.platform_score).toFixed(4) : "--");
      setHTML("#trend-suggestions", escapeHtml(t("training.suggestions.empty")));
      const badge = qs("#trend-health-badge");
      if (badge) {
        const label = isSequenceTrainingRecord(run) ? sequenceBackendLabel(run) : "Good";
        badge.className = "status-badge Good";
        badge.textContent = label;
      }
      return;
    }

    setText("#trend-best-epoch", run.best_epoch || "--");
    setText("#trend-platform-score", run.platform_score !== undefined ? Number(run.platform_score).toFixed(4) : "--");

    const health = run.health;
    const badge = qs("#trend-health-badge");
    if (badge) {
      badge.textContent = health.health_status || "Good";
      badge.className = `status-badge ${health.health_status || "Good"}`;
    }

    const suggestions = health.suggestions || [];
    setHTML("#trend-suggestions", suggestions.length ? suggestions.map((item) => `<div>- ${escapeHtml(item)}</div>`).join("") : escapeHtml(t("training.suggestions.empty")));
  } catch (err) {
    console.error("updateTrendDiagnostic error", err);
  }
}

function updateChartVisualization() {
  const grid = qs("#metrics-chart-grid");
  if (!grid) return;

  metricsCharts.forEach((chart) => chart.destroy());
  metricsCharts = [];
  grid.replaceChildren();

  if (!currentChartData || !currentChartData.epochs || currentChartData.epochs.length === 0) {
    grid.dataset.chartCount = "0";
    grid.dataset.chartMaxEpoch = "0";
    grid.dataset.chartPointCount = "0";
    const empty = document.createElement("div");
    empty.className = "metrics-chart-empty";
    empty.textContent = t("training.metrics.emptyTitle");
    grid.appendChild(empty);
    return;
  }

  const epochs = currentChartData.epochs;
  const chartMaxEpoch = getChartMaxEpoch(currentChartData, epochs);
  const chartLabels = Array.from({ length: chartMaxEpoch }, (_, index) => index + 1);
  grid.dataset.chartMaxEpoch = String(chartMaxEpoch);
  grid.dataset.chartPointCount = String(epochs.length);
  const showRaw = qs("#chart-show-raw")?.checked !== false;
  const showSmooth = qs("#chart-show-smooth")?.checked !== false;
  const alpha = Number(qs("#chart-ema-alpha")?.value || 0.25);

  const raw = currentChartData.raw || {};
  
  // Training UI helper
  const computeEma = (arr) => {
    if (!arr || arr.length === 0) return [];
    const ema = [];
    let curr = Number.isFinite(Number(arr[0])) ? Number(arr[0]) : 0;
    for (const val of arr) {
      const numeric = Number(val);
      if (!Number.isFinite(numeric)) {
        ema.push(null);
        continue;
      }
      curr = alpha * numeric + (1 - alpha) * curr;
      ema.append ? ema.push(curr) : ema.push(curr); // Training UI helper
    }
    return ema;
  };

  // Training UI helper
  let keysToRender = [];
  let colors = {
    primary1: { raw: "rgba(59, 130, 246, 0.4)", smooth: "#3b82f6" }, // mAP50-95
    primary2: { raw: "rgba(16, 185, 129, 0.4)", smooth: "#10b981" }, // mAP50
    loss1: { raw: "rgba(239, 68, 68, 0.4)", smooth: "#ef4444" }, // box loss
    loss2: { raw: "rgba(245, 158, 11, 0.4)", smooth: "#f59e0b" }, // seg loss
    loss3: { raw: "rgba(139, 92, 246, 0.4)", smooth: "#8b5cf6" }, // cls loss
  };

  if (activeChartTab === "primary") {
    // Training UI helper
    const map50_95_key = "metrics/mAP50-95(M)" in raw ? "metrics/mAP50-95(M)" : "metrics/mAP50-95(B)";
    const map50_key = "metrics/mAP50(M)" in raw ? "metrics/mAP50(M)" : "metrics/mAP50(B)";
    
    keysToRender = [
      { key: map50_95_key, label: "mAP50-95", color: colors.primary1 },
      { key: map50_key, label: "mAP50", color: colors.primary2 },
      { key: "metrics/precision(M)" in raw ? "metrics/precision(M)" : "metrics/precision(B)", label: "Precision", color: colors.loss2 },
      { key: "metrics/recall(M)" in raw ? "metrics/recall(M)" : "metrics/recall(B)", label: "Recall", color: colors.loss3 }
    ].filter(k => k.key in raw);
  } else if (activeChartTab === "loss") {
    // Training UI helper
    const losses = [
      { key: "train/box_loss", label: "Train Box Loss", color: colors.loss1 },
      { key: "val/box_loss", label: "Val Box Loss", color: colors.primary1 },
      { key: "train/seg_loss", label: "Train Seg Loss", color: colors.loss2 },
      { key: "val/seg_loss", label: "Val Seg Loss", color: colors.primary2 },
      { key: "train/cls_loss", label: "Train Cls Loss", color: colors.loss3 }
    ];
    keysToRender = losses.filter(l => l.key in raw);
  } else if (activeChartTab === "box") {
    keysToRender = [
      { key: "metrics/mAP50-95(B)", label: "Box mAP50-95", color: colors.primary1 },
      { key: "metrics/mAP50(B)", label: "Box mAP50", color: colors.primary2 },
      { key: "metrics/precision(B)", label: "Box Precision", color: colors.loss2 },
      { key: "metrics/recall(B)", label: "Box Recall", color: colors.loss3 }
    ].filter(k => k.key in raw);
  } else if (activeChartTab === "mask") {
    keysToRender = [
      { key: "metrics/mAP50-95(M)", label: "Mask mAP50-95", color: colors.primary1 },
      { key: "metrics/mAP50(M)", label: "Mask mAP50", color: colors.primary2 },
      { key: "metrics/precision(M)", label: "Mask Precision", color: colors.loss2 },
      { key: "metrics/recall(M)", label: "Mask Recall", color: colors.loss3 }
    ].filter(k => k.key in raw);
  } else if (activeChartTab === "hardware") {
    keysToRender = [
      { key: "gpu_usage", label: "GPU Usage (%)", color: colors.primary1 },
      { key: "vram_used_mb", label: "VRAM Used (MB)", color: colors.primary2 }
    ].filter(k => k.key in raw);
  }

  if (currentChartData.architecture === "rnn") {
    if (activeChartTab === "primary") {
      const isRegression = isRnnRegressionMetrics(currentChartData);
      keysToRender = (isRegression
        ? [
            { key: "val/mae", label: "MAE", color: colors.primary1 },
            { key: "val/rmse", label: "RMSE", color: colors.primary2 }
          ]
        : [
            { key: "val/macro_f1", label: "Macro-F1", color: colors.primary1 },
            { key: "val/accuracy", label: "Accuracy", color: colors.primary2 }
          ]).filter(k => k.key in raw);
    } else if (activeChartTab === "loss") {
      keysToRender = [
        { key: "train/loss", label: "Train Loss", color: colors.loss1 },
        { key: "val/loss", label: "Val Loss", color: colors.primary1 }
      ].filter(k => k.key in raw);
    } else if (["box", "mask", "hardware"].includes(activeChartTab)) {
      keysToRender = [];
    }
  }

  if (keysToRender.length === 0 || (!showRaw && !showSmooth)) {
    grid.dataset.chartCount = "0";
    const empty = document.createElement("div");
    empty.className = "metrics-chart-empty";
    empty.textContent = t("training.metrics.noTabMetrics");
    grid.appendChild(empty);
    return;
  }

  const isLight = document.body.dataset.theme === "light";
  const gridColor = isLight ? "#e2e8f0" : "#2b3441";
  const textColor = isLight ? "#5d6b7d" : "#95a1b1";

  keysToRender.forEach((item) => {
    const rawData = raw[item.key] || [];
    if (rawData.length === 0) return;

    const card = document.createElement("article");
    card.className = "metric-chart-card";
    card.dataset.metricKey = item.key;
    const header = document.createElement("div");
    header.className = "metric-chart-card-header";
    const title = document.createElement("h3");
    title.textContent = item.label;
    const latestLabel = document.createElement("span");
    const latestValue = [...rawData].reverse().find((value) => Number.isFinite(Number(value)));
    latestLabel.textContent = `${t("training.metrics.latest")}: ${metricValue(latestValue, 5)}`;
    header.append(title, latestLabel);
    const canvasWrap = document.createElement("div");
    canvasWrap.className = "metric-chart-canvas-wrap";
    const canvas = document.createElement("canvas");
    canvas.dataset.metricKey = item.key;
    canvasWrap.appendChild(canvas);
    card.append(header, canvasWrap);
    grid.appendChild(card);

    const datasets = [];
    const expandedRawData = expandSeriesToEpochRange(rawData, epochs, chartMaxEpoch);
    if (showRaw) {
      datasets.push({
        label: t("training.metrics.raw"),
        data: expandedRawData,
        borderColor: item.color.raw,
        backgroundColor: "transparent",
        borderWidth: 1.5,
        pointRadius: 1,
        tension: 0.1
      });
    }
    if (showSmooth) {
      const smoothData = computeEma(rawData);
      datasets.push({
        label: "EMA",
        data: expandSeriesToEpochRange(smoothData, epochs, chartMaxEpoch),
        borderColor: item.color.smooth,
        backgroundColor: "transparent",
        borderWidth: 2.5,
        pointRadius: 2,
        tension: 0.2
      });
    }

    const chart = new Chart(canvas, {
      type: "line",
      data: { labels: chartLabels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { labels: { color: textColor, font: { family: "Inter", size: 11 } } },
          tooltip: { mode: "index", intersect: false }
        },
        scales: {
          x: {
            grid: { color: gridColor },
            ticks: { color: textColor, font: { family: "Inter" } },
            title: { display: true, text: "Epoch", color: textColor }
          },
          y: {
            beginAtZero: false,
            grace: "8%",
            grid: { color: gridColor },
            ticks: { color: textColor, font: { family: "Inter" } },
            title: { display: true, text: item.label, color: textColor }
          }
        }
      }
    });
    canvas.dataset.chartDatasetCount = String(datasets.length);
    metricsCharts.push(chart);
  });
  grid.dataset.chartCount = String(metricsCharts.length);
}

function getChartMaxEpoch(chartData, epochs = []) {
  const configuredTotal = Number(chartData?.total_epochs || appState.trainingStatus?.total_epochs || qs("#train-epochs")?.value || 0);
  const lastEpoch = Math.max(0, ...epochs.map((epoch) => Number(epoch) || 0));
  return Math.max(1, configuredTotal || lastEpoch || epochs.length || 1);
}

function expandSeriesToEpochRange(values = [], epochs = [], maxEpoch = 1) {
  const expanded = Array.from({ length: maxEpoch }, () => null);
  values.forEach((value, index) => {
    const epoch = Number(epochs[index] ?? index + 1);
    if (!Number.isFinite(epoch) || epoch < 1 || epoch > maxEpoch) return;
    expanded[epoch - 1] = value;
  });
  return expanded;
}

// Training UI helper
function updateReportTabImage() {
  if (!appState.currentProjectId) return;
  const runId = lastLoadedRunId || "train";
  
  const resultsImg = qs("#static-report-img");
  const downloadPngBtn = qs("#btn-download-results-png");
  const downloadCsvBtn = qs("#btn-download-results-csv");

  const resultsPngUrl = `/api/projects/${appState.currentProjectId}/train/runs/${runId}/artifacts/download/results.png`;
  const resultsCsvUrl = `/api/projects/${appState.currentProjectId}/train/runs/${runId}/artifacts/download/results.csv`;

  if (resultsImg) {
    resultsImg.src = resultsPngUrl;
    resultsImg.onerror = () => {
      resultsImg.removeAttribute("src");
      resultsImg.alt = t("training.reportImageUnavailable");
      resultsImg.classList.add("hidden");
    };
  }
  if (downloadPngBtn) downloadPngBtn.href = resultsPngUrl;
  if (downloadCsvBtn) downloadCsvBtn.href = resultsCsvUrl;
}

// Training UI helper
function renderEpochHistoryTable(data) {
  const tbody = qs("#epoch-history-rows");
  if (!tbody) return;

  if (!data || !data.epochs || data.epochs.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding:16px; color:var(--text-muted);">${escapeHtml(t("training.logs.noEpoch"))}</td></tr>`;
    return;
  }

  const epochs = data.epochs;
  const raw = data.raw || {};
  if (data.architecture === "rnn") {
    const isRegression = isRnnRegressionMetrics(data);
    setText("#epoch-loss-header", "Val Loss");
    setText("#epoch-primary-header", isRegression ? "MAE" : "Accuracy");
    setText("#epoch-secondary-header", isRegression ? "RMSE" : "Macro-F1");
    setText("#epoch-tertiary-header", "Train Loss");
    setText("#epoch-quaternary-header", "Task");
    const rows = [];
    for (let i = epochs.length - 1; i >= 0; i -= 1) {
      const ep = epochs[i];
      const primary = isRegression ? raw["val/mae"]?.[i] : raw["val/accuracy"]?.[i];
      const secondary = isRegression ? raw["val/rmse"]?.[i] : raw["val/macro_f1"]?.[i];
      rows.push(`<tr><td><strong>${ep}</strong></td><td><code>${metricValue(raw["val/loss"]?.[i], 4)}</code></td><td>${metricValue(primary, isRegression ? 4 : 3)}</td><td>${metricValue(secondary, isRegression ? 4 : 3)}</td><td>${metricValue(raw["train/loss"]?.[i], 4)}</td><td>${isRegression ? "Regression" : "Classification"}</td><td><span class="badge badge-success">Completed</span></td></tr>`);
    }
    tbody.innerHTML = rows.join("");
    return;
  }

  setText("#epoch-loss-header", "Loss");
  setText("#epoch-primary-header", "mAP50(M)");
  setText("#epoch-secondary-header", "mAP50-95(M)");
  setText("#epoch-tertiary-header", "Precision(M)");
  setText("#epoch-quaternary-header", "Recall(M)");
  const mAP50Key = "metrics/mAP50(M)" in raw ? "metrics/mAP50(M)" : "metrics/mAP50(B)";
  const mAP5095Key = "metrics/mAP50-95(M)" in raw ? "metrics/mAP50-95(M)" : "metrics/mAP50-95(B)";
  const precisionKey = "metrics/precision(M)" in raw ? "metrics/precision(M)" : "metrics/precision(B)";
  const recallKey = "metrics/recall(M)" in raw ? "metrics/recall(M)" : "metrics/recall(B)";
  const lossKey = "train/box_loss" in raw ? "train/box_loss" : "train/seg_loss";

  const rows = [];
  for (let i = epochs.length - 1; i >= 0; i -= 1) {
    const ep = epochs[i];
    const loss = raw[lossKey] ? Number(raw[lossKey][i]).toFixed(4) : "--";
    const map50 = raw[mAP50Key] ? Number(raw[mAP50Key][i]).toFixed(3) : "--";
    const map5095 = raw[mAP5095Key] ? Number(raw[mAP5095Key][i]).toFixed(3) : "--";
    const precision = raw[precisionKey] ? Number(raw[precisionKey][i]).toFixed(3) : "--";
    const recall = raw[recallKey] ? Number(raw[recallKey][i]).toFixed(3) : "--";
    rows.push(`<tr><td><strong>${ep}</strong></td><td><code>${loss}</code></td><td>${map50}</td><td>${map5095}</td><td>${precision}</td><td>${recall}</td><td><span class="badge badge-success">Completed</span></td></tr>`);
  }

  tbody.innerHTML = rows.join("");
}

function renderArtifactList(artifacts, runId) {
  const container = qs("#artifact-list-container");
  if (!container) return;

  if (!artifacts || artifacts.length === 0) {
    container.innerHTML = `<div class="empty-state">${escapeHtml(t("training.artifacts.empty"))}</div>`;
    return;
  }

  const rows = artifacts.map((art) => {
    const filename = art.filename;
    const sizeKb = (art.size / 1024).toFixed(1);
    const downloadUrl = `/api/projects/${appState.currentProjectId}/train/runs/${runId}/artifacts/download/${filename}?path=${encodeURIComponent(art.rel_path)}`;
    let actions = `<a href="${downloadUrl}" class="btn btn-secondary btn-sm" target="_blank" download><i class="fa-solid fa-download"></i> Download</a>`;
    if (filename === "best.pt" && currentChartData?.architecture !== "rnn") {
      actions += `<button class="btn btn-primary btn-sm" onclick="exportArtifactOnnx('${runId}')" style="margin-left: 6px;"><i class="fa-solid fa-file-export"></i> Export ONNX</button>`;
    }
    return `<div class="artifact-row"><div class="art-info"><span>${escapeHtml(filename)}</span><small>Size: ${sizeKb} KB | Path: ${escapeHtml(art.rel_path)}</small></div><div style="display:flex; align-items:center;">${actions}</div></div>`;
  });

  container.innerHTML = rows.join("");
}

window.exportArtifactOnnx = async function(runId) {
  eventBus.emit("toast", "Exporting best.pt to ONNX...");
  try {
    const res = await apiFetch(`/api/projects/${appState.currentProjectId}/train/runs/${runId}/export-onnx`, { method: "POST" });
    if (res.success) {
      eventBus.emit("toast", "ONNX export complete. Check the exports folder.");
      await loadRunArtifacts(runId);
    }
  } catch (err) {
    eventBus.emit("toast", `ONNX export failed: ${err.message}`);
  }
};

// Training UI helper
async function renderRunHistoryTable() {
  const tbody = qs("#run-history-rows");
  if (!tbody) return;

  const emptyRow = `<tr><td colspan="10" class="text-center" style="padding:16px; color:var(--text-muted);">${escapeHtml(t("training.runHistory.empty"))}</td></tr>`;
  if (!appState.currentProjectId) {
    tbody.innerHTML = emptyRow;
    return;
  }

  try {
    const runs = await apiFetch(`/api/projects/${appState.currentProjectId}/train/runs`);
    if (!runs || runs.length === 0) {
      tbody.innerHTML = emptyRow;
      return;
    }

    const rows = runs.map((run) => {
      const runId = run.run_id;
      const date = run.completed_at ? new Date(run.completed_at).toLocaleString() : "--";
      const config = run.best_metrics || {};
      const runTaskType = String(run.task_type || "").toLowerCase();
      const isRnnRun = isSequenceTrainingRecord(run);
      const isSequenceRegression = isRnnRun && (
        runTaskType.includes("regression") ||
        config["val/mae"] !== undefined ||
        config["val/rmse"] !== undefined
      );
      const isSeg = runTaskType.includes("segmentation") || runTaskType.includes("seg");
      const suffix = isSeg ? "(M)" : "(B)";
      const metric1 = isRnnRun
        ? isSequenceRegression
          ? labeledMetric("MAE", config["val/mae"], 4)
          : labeledMetric("Acc", config["val/accuracy"])
        : labeledMetric("mAP50", config[`metrics/mAP50${suffix}`]);
      const metric2 = isRnnRun
        ? isSequenceRegression
          ? labeledMetric("RMSE", config["val/rmse"], 4)
          : labeledMetric("Macro-F1", config["val/macro_f1"])
        : labeledMetric("mAP50-95", config[`metrics/mAP50-95${suffix}`]);
      let statusBadge = `<span class="badge badge-success">Completed</span>`;
      if (run.status === "failed") statusBadge = `<span class="badge badge-danger">Failed</span>`;
      else if (run.status === "stopped") statusBadge = `<span class="badge badge-warning">Stopped</span>`;
      else if (run.status === "training") statusBadge = `<span class="badge badge-success fa-spin"><i class="fa-solid fa-spinner"></i> Running</span>`;
      return `<tr data-run-id="${escapeHtml(runId)}" class="${runId === lastLoadedRunId ? "row-success" : ""}" style="cursor:pointer;"><td><code>${escapeHtml(runId)}</code></td><td>${date}</td><td>${escapeHtml(run.model || run.backend || "--")}</td><td>${run.epochs || run.best_epoch || "--"}</td><td>${isRnnRun ? "sequence" : run.imgsz || "--"}</td><td>${run.batch_size || "--"}</td><td>${metric1}</td><td>${metric2}</td><td>${statusBadge}</td><td><button class="btn btn-secondary btn-sm btn-view-run" data-run-id="${escapeHtml(runId)}"><i class="fa-solid fa-chart-line"></i> View</button></td></tr>`;
    });

    tbody.innerHTML = rows.join("");
    qsa("#run-history-rows tr").forEach((row) => {
      const runId = row.dataset.runId;
      row.querySelector(".btn-view-run")?.addEventListener("click", async (event) => {
        event.stopPropagation();
        await selectRunIdAndRender(runId);
      });
      row.addEventListener("click", async () => selectRunIdAndRender(runId));
    });
  } catch (err) {
    console.error("renderRunHistoryTable error", err);
    tbody.innerHTML = `<tr><td colspan="10" class="text-center" style="padding:16px; color:var(--text-danger);">Failed to load run history.</td></tr>`;
  }
}

async function selectRunIdAndRender(runId) {
  eventBus.emit("toast", `Loading run ${runId} metrics...`);
  await loadRunMetrics(runId);
  
  // Training UI helper
  qsa("#run-history-rows tr").forEach((row) => {
    row.classList.toggle("row-success", row.dataset.runId === runId);
  });
}

// Training UI helper
function startMonitorWebSocket() {
  if (!appState.currentProjectId) return;
  
  // Training UI helper
  if (appState.wsConn) {
    if (appState.wsConn.readyState === WebSocket.OPEN || appState.wsConn.readyState === WebSocket.CONNECTING) {
      return;
    }
    try {
      appState.wsConn.close();
    } catch (e) {}
  }
  
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  appState.wsConn = new WebSocket(`${protocol}//${window.location.host}/api/projects/${appState.currentProjectId}/monitor`);
  scheduleTrainingStatusPoll(4000);
  
  appState.wsConn.onmessage = (event) => {
    try {
      applyTrainingStatusUpdate(JSON.parse(event.data));
    } catch (error) {
      console.error("Invalid training monitor message", error);
      scheduleTrainingStatusPoll(250);
    }
  };
  
  appState.wsConn.onclose = () => {
    appState.wsConn = null;
    if (ACTIVE_TRAINING_STATUSES.has(appState.trainingStatus?.status)) {
      scheduleTrainingStatusPoll(250);
    }
  };
  appState.wsConn.onerror = () => {
    eventBus.emit("toast", "Training monitor WebSocket failed.");
    scheduleTrainingStatusPoll(250);
  };
}

function applyTrainingStatusUpdate(data) {
  if (!data || typeof data !== "object") return;
  const previousStatus = appState.trainingStatus?.status || "idle";
  appState.trainingStatus = data;
  renderTrainingMonitor();
  eventBus.emit("state-changed");

  if (TERMINAL_TRAINING_STATUSES.has(data.status)) {
    stopTrainingStatusPolling();
    if (appState.wsConn) {
      try {
        appState.wsConn.close();
      } catch (error) {}
    }
    if (previousStatus !== data.status) eventBus.emit("refresh-project");
    return;
  }

  if (ACTIVE_TRAINING_STATUSES.has(data.status)) {
    scheduleTrainingStatusPoll(4000);
  }
}

function scheduleTrainingStatusPoll(delay = 4000) {
  if (!appState.currentProjectId || !ACTIVE_TRAINING_STATUSES.has(appState.trainingStatus?.status)) return;
  if (trainingStatusPollTimer) window.clearTimeout(trainingStatusPollTimer);
  trainingStatusPollTimer = window.setTimeout(refreshTrainingStatusFromApi, delay);
}

async function refreshTrainingStatusFromApi() {
  trainingStatusPollTimer = null;
  if (trainingStatusPollInFlight || !appState.currentProjectId) return;
  trainingStatusPollInFlight = true;
  try {
    const data = await apiFetch(`/api/projects/${appState.currentProjectId}/train/status`);
    applyTrainingStatusUpdate(data);
  } catch (error) {
    console.error("Training status fallback poll failed", error);
    scheduleTrainingStatusPoll(2000);
  } finally {
    trainingStatusPollInFlight = false;
  }
}

function stopTrainingStatusPolling() {
  if (trainingStatusPollTimer) {
    window.clearTimeout(trainingStatusPollTimer);
    trainingStatusPollTimer = null;
  }
}
