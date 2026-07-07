import { eventBus } from "../event_bus.js";
import { appState } from "../state.js";
import { apiFetch } from "../api.js";
import { qs, qsa, escapeHtml, setText } from "../utils.js";

export const trainingModeState = {
  activeMode: "cnn",
  activeCnnPanel: "overview",
  activeRnnPanel: "overview",
  cnn: {
    backend: "ultralytics_yolo",
    trainingEnabled: true
  },
  rnn: {
    backend: "pytorch_lstm",
    trainingEnabled: false,
    readiness: null,
    config: null,
    configInspection: null,
    configValidation: null,
    windowSummary: null,
    configMismatches: [],
    configLoading: false,
    datasetImporting: false,
    readinessLoading: false,
    trainingStarting: false,
    modelCatalog: [],
    modelCatalogLoading: false,
    modelGuides: null,
    modelGuidesLoading: false,
    inferenceModels: [],
    inferenceLoading: false,
    inferenceRunning: false,
    inferenceResult: null,
    evaluationLoading: false,
    evaluationRuns: [],
    evaluationMetrics: null,
    evaluationArtifacts: [],
    evaluationRunId: "",
    evaluationRunMetrics: {},
    comparisonMetric: "macro_f1"
  }
};

export function initTrainingModeSidebar() {
  qsa("[data-training-mode]").forEach((button) => {
    button.addEventListener("click", () => setTrainingMode(button.dataset.trainingMode));
  });

  qsa("[data-rnn-nav]").forEach((button) => {
    button.addEventListener("click", () => {
      trainingModeState.activeMode = "rnn";
      trainingModeState.activeRnnPanel = button.dataset.rnnNav;
      if (trainingModeState.activeRnnPanel === "model-compare") {
        eventBus.emit("set-compare-architecture", "rnn");
        eventBus.emit("navigate", "model-compare");
        renderTrainingModeSidebar();
        renderTrainingWorkspace();
        return;
      }
      eventBus.emit("navigate", "training");
      ensureTrainingPageActive();
      renderTrainingModeSidebar();
      renderTrainingWorkspace();
      loadRnnConfig({ force: true });
      if (trainingModeState.activeRnnPanel === "sequence-test") loadRnnInferenceModels();
      if (trainingModeState.activeRnnPanel === "evaluation") loadRnnEvaluation({ force: true });
    });
  });

  qsa("[data-cnn-nav]").forEach((button) => {
    button.addEventListener("click", () => {
      const nav = button.dataset.cnnNav;
      const page = button.dataset.page || nav || "dashboard";
      trainingModeState.activeMode = "cnn";
      trainingModeState.activeCnnPanel = nav === "training" ? "training" : "overview";
      if (nav === "model-compare") eventBus.emit("set-compare-architecture", "cnn");
      eventBus.emit("navigate", page);
      renderTrainingModeSidebar();
      renderTrainingWorkspace();
    });
  });

  qsa("[data-mode-nav]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      qsa("[data-mode-nav]").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      if (button.dataset.modeNav === "overview") {
        trainingModeState.activeCnnPanel = "overview";
        trainingModeState.activeRnnPanel = "overview";
        eventBus.emit("navigate", trainingModeState.activeMode === "cnn" ? "dashboard" : "training");
        renderTrainingModeSidebar();
        renderTrainingWorkspace();
        if (trainingModeState.activeMode === "rnn") loadRnnConfig({ force: true });
        return;
      }
      if (button.dataset.modeNav === "history" || button.dataset.modeNav === "settings") {
        eventBus.emit("navigate", button.dataset.modeNav);
        renderTrainingModeSidebar();
        renderTrainingWorkspace();
      }
    });
  });

  initRnnPreviewEvents();
  loadRnnModelGuides();
  renderTrainingModeSidebar();
  renderTrainingWorkspace();
}

export function setTrainingMode(mode) {
  if (!["cnn", "rnn"].includes(mode) || trainingModeState.activeMode === mode) return;
  trainingModeState.activeMode = mode;
  if (mode === "cnn") trainingModeState.activeCnnPanel = "overview";
  if (mode === "rnn") trainingModeState.activeRnnPanel = "overview";
  eventBus.emit("navigate", mode === "cnn" ? "dashboard" : "training");
  if (mode === "rnn") ensureTrainingPageActive();
  renderTrainingModeSidebar();
  renderTrainingWorkspace();
  if (mode === "rnn") loadRnnConfig({ force: true });
}

function ensureTrainingPageActive() {
  appState.currentPage = "training";
  qsa(".page").forEach((page) => {
    page.classList.toggle("active", page.id === "page-training");
  });
}

export function syncTrainingModeForProject(project, targetPage = "dashboard") {
  const taskType = String(project?.task_type || "").toLowerCase();
  const isRnnProject = taskType.includes("sequence") || taskType.includes("time_series") || taskType.includes("rnn");

  if (isRnnProject) {
    trainingModeState.activeMode = "rnn";
    trainingModeState.activeRnnPanel = "overview";
    return;
  }

  trainingModeState.activeMode = "cnn";
  trainingModeState.activeCnnPanel = targetPage === "training" ? "training" : "overview";
}

export function renderTrainingModeSidebar() {
  qsa("[data-training-mode]").forEach((button) => {
    button.classList.toggle("active", button.dataset.trainingMode === trainingModeState.activeMode);
  });

  qs("#cnn-mode-nav")?.classList.toggle("hidden", trainingModeState.activeMode !== "cnn");
  qs("#rnn-mode-nav")?.classList.toggle("hidden", trainingModeState.activeMode !== "rnn");

  qsa("[data-rnn-nav]").forEach((button) => {
    button.classList.toggle("active", button.dataset.rnnNav === trainingModeState.activeRnnPanel);
  });

  qsa("[data-cnn-nav]").forEach((button) => {
    const nav = button.dataset.cnnNav;
    button.classList.toggle(
      "active",
      trainingModeState.activeMode === "cnn" && (
        nav === "training"
          ? appState.currentPage === "training" && trainingModeState.activeCnnPanel === "training"
          : appState.currentPage === nav
      )
    );
  });

  qsa("[data-mode-nav]").forEach((button) => {
    button.classList.toggle(
      "active",
      button.dataset.modeNav === "overview"
        ? (
          trainingModeState.activeMode === "cnn"
            ? appState.currentPage === "dashboard"
            : appState.currentPage === "training" && trainingModeState.activeRnnPanel === "overview"
        )
        : button.dataset.modeNav === appState.currentPage
    );
  });
}

export function renderTrainingWorkspace() {
  const isCnn = trainingModeState.activeMode === "cnn";
  const isRnnEvaluation = !isCnn && appState.currentPage === "training" && trainingModeState.activeRnnPanel === "evaluation";
  qs("#cnn-workspace")?.classList.toggle("hidden", !isCnn);
  qs("#cnn-workspace")?.classList.toggle("active", isCnn);
  qs("#rnn-workspace")?.classList.toggle("hidden", isCnn);
  qs("#rnn-workspace")?.classList.toggle("active", !isCnn);
  qs("#rnn-header-actions")?.classList.toggle("hidden", isCnn);

  qsa("[data-rnn-panel]").forEach((panel) => {
    const isActive = panel.dataset.rnnPanel === trainingModeState.activeRnnPanel;
    panel.classList.toggle("active", isActive);
  });
  qsa("[data-cnn-panel]").forEach((panel) => {
    const isActive = panel.dataset.cnnPanel === trainingModeState.activeCnnPanel;
    panel.classList.toggle("active", isActive);
  });

  renderRnnReadiness();
  renderRnnSidebarReadiness(isCnn);
  toggleRnnEvaluationRightPanel(isRnnEvaluation);
  if (isRnnEvaluation) {
    loadRnnEvaluation();
  }
}

export function isRnnTrainingWorkspaceActive(pageId = appState.currentPage) {
  return pageId === "training" && trainingModeState.activeMode === "rnn";
}

function renderRnnSidebarReadiness(isCnn) {
  const section = qs("#section-rnn-readiness");
  if (!section) return;
  const visible = !isCnn && appState.currentPage === "training" && trainingModeState.activeRnnPanel !== "evaluation";
  section.classList.toggle("hidden", !visible);
}

function toggleRnnEvaluationRightPanel(visible) {
  const evalSection = qs("#section-rnn-eval-summary");
  evalSection?.classList.toggle("hidden", !visible);
  const hidePageGuards = visible || (appState.currentPage === "training" && trainingModeState.activeMode === "rnn");
  [
    "#section-project-context",
    "#section-page-context"
  ].forEach((selector) => {
    const section = qs(selector);
    if (section) section.style.display = visible ? "none" : "";
  });
  const pageGuards = qs("#section-page-guards");
  if (pageGuards) pageGuards.style.display = hidePageGuards ? "none" : "";
  [qs("#next-actions-list")?.closest(".summary-section"), qs("#warning-list")?.closest(".summary-section")]
    .filter(Boolean)
    .forEach((section) => {
      section.style.display = visible ? "none" : "";
    });
}

export function initRnnPreviewEvents() {
  preferGpuDevice("#rnn-device");
  preferGpuDevice("#rnn-inference-device");

  qs("#rnn-create-project")?.addEventListener("click", () => {
    eventBus.emit("open-create-project-modal", {
      taskType: "sequence_classification",
      mode: "rnn"
    });
  });

  qsa(".rnn-disabled-action-hitbox").forEach((hitbox) => hitbox.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (button && !button.disabled) return;
    event.preventDefault();
    eventBus.emit("toast", getRnnStartBlockerMessage());
  }));
  ["#rnn-sequence-length", "#rnn-stride", "#rnn-horizon"].forEach((selector) => {
    qs(selector)?.addEventListener("change", () => saveRnnFeatureConfig({ silent: true }));
  });
  qs("#rnn-refresh-config")?.addEventListener("click", () => loadRnnConfig({ force: true }));
  qs("#rnn-dataset-file")?.addEventListener("change", updateRnnDatasetDropzone);
  qs("#rnn-dataset-dropzone")?.addEventListener("click", () => qs("#rnn-dataset-file")?.click());
  qs("#rnn-dataset-dropzone")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") qs("#rnn-dataset-file")?.click();
  });
  ["dragenter", "dragover"].forEach((eventName) => {
    qs("#rnn-dataset-dropzone")?.addEventListener(eventName, (event) => {
      event.preventDefault();
      qs("#rnn-dataset-dropzone")?.classList.add("drag-over");
    });
  });
  ["dragleave", "drop"].forEach((eventName) => {
    qs("#rnn-dataset-dropzone")?.addEventListener(eventName, (event) => {
      event.preventDefault();
      qs("#rnn-dataset-dropzone")?.classList.remove("drag-over");
    });
  });
  qs("#rnn-dataset-dropzone")?.addEventListener("drop", (event) => {
    const file = event.dataTransfer?.files?.[0];
    const input = qs("#rnn-dataset-file");
    if (file && input) {
      const transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
      updateRnnDatasetDropzone();
    }
  });
  qs("#rnn-import-dataset")?.addEventListener("click", importRnnDataset);
  qs("#rnn-feature-columns")?.addEventListener("input", renderRnnFeatureChips);
  qs("#rnn-save-feature-config")?.addEventListener("click", () => saveRnnFeatureConfig());
  qs("#rnn-model-family")?.addEventListener("change", () => {
    syncRnnModelSelection();
    renderRnnModelGuide();
    updateRnnStartControls();
  });
  qs("#btn-rnn-import-model-package")?.addEventListener("click", () => {
    eventBus.emit("open-model-import", {
      importType: "rnn_package",
      taskFamily: getSelectedRnnTaskHead() === "regression" ? "sequence_regression" : "sequence_classification"
    });
  });
  qs("#rnn-task-head")?.addEventListener("change", () => {
    renderRnnModelSelector();
    syncRnnModelSelection();
    renderRnnModelGuide();
    saveRnnFeatureConfig({ silent: true });
  });
  ["#rnn-start-disabled", "#rnn-training-disabled-action"].forEach((selector) => {
    qs(selector)?.addEventListener("click", startRnnTraining);
  });
  qs("#rnn-refresh-models")?.addEventListener("click", () => loadRnnInferenceModels({ force: true }));
  qs("#rnn-refresh-evaluation")?.addEventListener("click", () => loadRnnEvaluation({ force: true }));
  qsa("[data-rnn-compare-metric]").forEach((button) => {
    button.addEventListener("click", () => {
      trainingModeState.rnn.comparisonMetric = button.dataset.rnnCompareMetric || "macro_f1";
      renderRnnEvaluation();
    });
  });
  qs("#rnn-inference-model")?.addEventListener("change", updateRnnInferenceControls);
  qs("#rnn-inference-csv-file")?.addEventListener("change", () => {
    if (qs("#rnn-inference-csv-file")?.files?.[0]) {
      const pathInput = qs("#rnn-inference-csv-path");
      if (pathInput) pathInput.value = "";
    }
    updateRnnInferenceControls();
  });
  qs("#rnn-inference-csv-path")?.addEventListener("input", () => {
    if (qs("#rnn-inference-csv-path")?.value?.trim()) {
      const fileInput = qs("#rnn-inference-csv-file");
      if (fileInput) fileInput.value = "";
    }
    updateRnnInferenceControls();
  });
  qs("#rnn-run-sequence-inference")?.addEventListener("click", runRnnSequenceInference);
}

async function loadRnnReadiness(options = {}) {
  if (!appState.currentProjectId || (trainingModeState.rnn.readinessLoading && !options.force)) {
    renderRnnReadiness();
    return;
  }

  trainingModeState.rnn.readinessLoading = true;
  renderRnnReadiness();
  try {
    const params = new URLSearchParams({
      sequence_length: qs("#rnn-sequence-length")?.value || "16",
      stride: qs("#rnn-stride")?.value || "8",
      horizon: qs("#rnn-horizon")?.value || "1"
    });
    trainingModeState.rnn.readiness = await apiFetch(`/api/projects/${appState.currentProjectId}/rnn/readiness?${params.toString()}`);
  } catch (err) {
    trainingModeState.rnn.readiness = {
      status: "not_ready",
      ready: false,
      training_enabled: false,
      message: err.message || "RNN readiness check failed.",
      summary: { manifest: {}, csv: {}, source: "none", ready_requirements: {} },
      checks: [{ key: "api_error", label: "Readiness API", status: "fail", message: err.message || "Request failed." }]
    };
  } finally {
    trainingModeState.rnn.readinessLoading = false;
    renderRnnReadiness();
  }
}

async function loadRnnConfig(options = {}) {
  if (!appState.currentProjectId) {
    await loadRnnModelCatalog({ force: options.force });
    renderRnnConfig();
    return;
  }
  if (trainingModeState.rnn.configLoading && !options.force) {
    renderRnnConfig();
    return;
  }
  trainingModeState.rnn.configLoading = true;
  renderRnnConfig();
  try {
    const payload = await apiFetch(`/api/projects/${appState.currentProjectId}/rnn/config`);
    trainingModeState.rnn.config = payload.config || null;
    trainingModeState.rnn.configInspection = payload.inspection || null;
    trainingModeState.rnn.configValidation = payload.validation || null;
    trainingModeState.rnn.windowSummary = payload.window || payload.validation?.window || null;
    trainingModeState.rnn.configMismatches = payload.mismatches || [];
    applyRnnConfigToForm();
    await loadRnnModelCatalog({ force: options.force });
    await loadRnnReadiness({ force: true });
  } catch (err) {
    eventBus.emit("toast", `RNN config load failed: ${err.message}`);
  } finally {
    trainingModeState.rnn.configLoading = false;
    renderRnnConfig();
  }
}

function applyRnnConfigToForm() {
  const config = trainingModeState.rnn.config || {};
  const setValue = (selector, value) => {
    const el = qs(selector);
    if (el && value !== undefined && value !== null) el.value = value;
  };
  setValue("#rnn-feature-columns", (config.feature_columns || []).join(", "));
  setValue("#rnn-target-column", config.target_column || "");
  setValue("#rnn-sequence-column", config.sequence_column || "");
  setValue("#rnn-time-column", config.time_column || "");
  setValue("#rnn-sequence-length", config.sequence_length || 16);
  setValue("#rnn-stride", config.stride || 8);
  setValue("#rnn-horizon", config.horizon || 1);
  setValue("#rnn-task-head", config.task_head || "classification");
  renderRnnFeatureChips();
  syncRnnModelSelection();
  renderRnnModelGuide();
}

function parseRnnFeatureInput() {
  const value = qs("#rnn-feature-columns")?.value || "";
  const seen = new Set();
  return value.split(/[,;\n\r]+/).map((item) => item.trim()).filter((item) => {
    if (!item || seen.has(item)) return false;
    seen.add(item);
    return true;
  });
}

async function saveRnnFeatureConfig(options = {}) {
  if (!appState.currentProjectId) {
    if (!options.silent) eventBus.emit("toast", "Open an RNN project before saving feature config.");
    return;
  }
  const payload = {
    feature_columns: parseRnnFeatureInput(),
    target_column: qs("#rnn-target-column")?.value?.trim() || "",
    sequence_column: qs("#rnn-sequence-column")?.value?.trim() || "",
    time_column: qs("#rnn-time-column")?.value?.trim() || "",
    sequence_length: Number(qs("#rnn-sequence-length")?.value || 16),
    stride: Number(qs("#rnn-stride")?.value || 8),
    horizon: Number(qs("#rnn-horizon")?.value || 1),
    task_head: qs("#rnn-task-head")?.value || "classification"
  };
  try {
    const result = await apiFetch(`/api/projects/${appState.currentProjectId}/rnn/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    trainingModeState.rnn.config = result.config || payload;
    trainingModeState.rnn.configInspection = result.inspection || trainingModeState.rnn.configInspection;
    trainingModeState.rnn.configValidation = result.validation || null;
    trainingModeState.rnn.windowSummary = result.window || result.validation?.window || null;
    trainingModeState.rnn.configMismatches = result.mismatches || [];
    renderRnnConfig(result.validation);
    await loadRnnReadiness({ force: true });
    if (!options.silent) eventBus.emit("toast", "RNN feature config saved.");
  } catch (err) {
    if (!options.silent) eventBus.emit("toast", `RNN feature config save failed: ${err.message}`);
  }
}

function updateRnnDatasetDropzone() {
  const file = qs("#rnn-dataset-file")?.files?.[0];
  const zone = qs("#rnn-dataset-dropzone");
  if (!zone) return;
  zone.classList.toggle("has-file", Boolean(file));
  const label = zone.querySelector("strong");
  if (label) label.textContent = file ? file.name : "拖入 CSV / ZIP 或點擊選擇檔案";
}

async function importRnnDataset() {
  if (!appState.currentProjectId) {
    eventBus.emit("toast", "Open an RNN project before importing sequence data.");
    return;
  }
  const file = qs("#rnn-dataset-file")?.files?.[0];
  if (!file) {
    eventBus.emit("toast", "Please select a CSV or ZIP file first.");
    return;
  }
  const lowerName = file.name.toLowerCase();
  if (!lowerName.endsWith(".csv") && !lowerName.endsWith(".zip")) {
    eventBus.emit("toast", "RNN sequence import only accepts .csv or .zip.");
    return;
  }
  trainingModeState.rnn.datasetImporting = true;
  renderRnnConfig();
  try {
    const form = new FormData();
    form.append("file", file);
    const result = await apiFetch(`/api/projects/${appState.currentProjectId}/rnn/dataset/import`, {
      method: "POST",
      body: form
    });
    trainingModeState.rnn.config = result.config || null;
    trainingModeState.rnn.configInspection = result.dataset?.inspection || result.inspection || null;
    trainingModeState.rnn.configValidation = result.validation || null;
    trainingModeState.rnn.windowSummary = result.window || result.validation?.window || null;
    trainingModeState.rnn.configMismatches = result.mismatches || [];
    applyRnnConfigToForm();
    await loadRnnReadiness({ force: true });
    eventBus.emit("toast", "RNN sequence dataset imported.");
  } catch (err) {
    eventBus.emit("toast", `RNN dataset import failed: ${err.message}`);
  } finally {
    trainingModeState.rnn.datasetImporting = false;
    renderRnnConfig();
  }
}

function renderRnnConfig(validation = null) {
  const inspection = trainingModeState.rnn.configInspection || {};
  const config = trainingModeState.rnn.config || {};
  const headers = inspection.headers || [];
  const files = inspection.files || [];
  const badge = qs("#rnn-dataset-badge");
  if (badge) {
    badge.className = `summary-badge ${files.length ? "badge-success" : "badge-warning"}`;
    badge.textContent = trainingModeState.rnn.datasetImporting ? "Importing" : files.length ? `${files.length} CSV` : "CSV required";
  }
  const featureDimInput = qs("#rnn-feature-dim");
  if (featureDimInput) featureDimInput.value = String((config.feature_columns || []).length || inspection.feature_dim || 0);
  const hash = config.feature_config_hash ? `hash ${String(config.feature_config_hash).slice(0, 8)}` : "No config";
  setText("#rnn-config-hash-badge", hash);
  const preview = qs("#rnn-sequence-dataset-preview");
  if (preview) {
    const rows = inspection.preview_rows || [];
    if (rows.length) {
      const cols = headers.slice(0, 8);
      preview.innerHTML = `<div class="rnn-preview-table-wrap"><table class="rnn-preview-table"><thead><tr>${cols.map((col) => `<th>${escapeHtml(col)}</th>`).join("")}</tr></thead><tbody>${rows.slice(0, 6).map((row) => `<tr>${cols.map((col) => `<td>${escapeHtml(row[col] ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    } else {
      preview.textContent = "sequence_id, timestep, feature_1, feature_2, target";
    }
  }
  renderRnnFeatureChips(validation);
  renderRnnWindowSummary(validation);
  renderRnnConfigMismatch();
  renderRnnModelGuide();
}

function renderRnnWindowSummary(validation = null) {
  const windowSummary = validation?.window || trainingModeState.rnn.windowSummary || trainingModeState.rnn.configValidation?.window || {};
  const badge = qs("#rnn-window-status-badge");
  const warning = qs("#rnn-window-warning");
  const summary = qs("#rnn-window-summary");
  const status = windowSummary.status || "warning";
  if (badge) {
    badge.className = `summary-badge ${status === "ok" ? "badge-success" : status === "error" ? "badge-danger" : "badge-warning"}`;
    badge.textContent = status === "ok" ? "Ready" : status === "error" ? "Invalid" : "Needs CSV";
  }
  if (summary) {
    const estimated = windowSummary.estimated_windows ?? "--";
    const sequences = windowSummary.sequence_count ?? "--";
    const minLength = windowSummary.min_sequence_length || "--";
    const maxLength = windowSummary.max_sequence_length || "--";
    summary.innerHTML = `
      <div><span>Estimated windows</span><strong>${escapeHtml(estimated)}</strong></div>
      <div><span>Sequence count</span><strong>${escapeHtml(sequences)}</strong></div>
      <div><span>Min / Max length</span><strong>${escapeHtml(minLength)} / ${escapeHtml(maxLength)}</strong></div>
    `;
  }
  if (warning) {
    const messages = [...(windowSummary.errors || []), ...(windowSummary.warnings || [])];
    warning.classList.toggle("hidden", !messages.length);
    warning.innerHTML = messages.length
      ? `<strong>Window config</strong><span>${messages.map((item) => escapeHtml(item)).join("<br>")}</span>`
      : "";
  }
}

function renderRnnFeatureChips(validation = null) {
  const list = qs("#rnn-feature-chip-list");
  if (!list) return;
  const headers = new Set(trainingModeState.rnn.configInspection?.headers || []);
  const validationStatus = new Map((validation?.feature_status || []).map((item) => [item.name, item]));
  const features = parseRnnFeatureInput();
  list.innerHTML = features.map((name) => {
    const exists = validationStatus.get(name)?.exists ?? headers.has(name);
    const cls = exists ? "valid" : "invalid";
    return `<span class="rnn-chip ${cls}">${escapeHtml(name)}${exists ? "" : " 繚 missing"}</span>`;
  }).join("");
}

function renderRnnConfigMismatch() {
  const box = qs("#rnn-config-mismatch-warning");
  if (!box) return;
  const mismatches = trainingModeState.rnn.configMismatches || [];
  box.classList.toggle("hidden", !mismatches.length);
  if (!mismatches.length) {
    box.textContent = "";
    return;
  }
  box.innerHTML = `<strong>Feature config mismatch</strong><span>${escapeHtml(mismatches.length)} previous RNN run(s) use different feature config. Existing runs are kept, but direct comparison may be inconsistent.</span>`;
}

function renderRnnReadiness() {
  const readiness = trainingModeState.rnn.readiness;
  const loading = trainingModeState.rnn.readinessLoading;
  const canStart = canStartRnnTraining();
  const badge = qs("#rnn-readiness-badge");
  if (badge) {
    badge.className = `summary-badge ${canStart ? "badge-success" : loading ? "badge-neutral" : "badge-warning"}`;
    badge.textContent = canStart ? "Ready" : loading ? "Checking" : readiness?.ready ? "Manifest only" : "Not Ready";
  }

  if (!readiness) {
    setText("#rnn-readiness-status", loading ? "Checking..." : "Not Ready / Preview");
    setText("#rnn-readiness-message", loading ? "Checking sequence manifest and CSV feature files..." : "Sequence CSV readiness summary appears here when a project is active.");
    const compactGrid = qs("#rnn-readiness-compact-grid");
    if (compactGrid) compactGrid.innerHTML = "";
    const list = qs("#rnn-readiness-checks");
    if (list) list.innerHTML = "";
    const details = qs("#rnn-readiness-details");
    if (details) details.open = false;
    updateRnnStartControls();
    return;
  }

  const manifest = readiness.summary?.manifest || {};
  const csv = readiness.summary?.csv || {};
  const requirements = readiness.summary?.ready_requirements || {};
  const source = readiness.summary?.source || "none";
  const splitCounts = source === "manifest" ? manifest.split_counts || {} : csv.split_counts || {};
  const splitText = Object.keys(splitCounts).length
    ? Object.entries(splitCounts).map(([key, value]) => `${key}: ${value}`).join(" / ")
    : "-- / -- / --";
  const featureDim = csv.feature_dim || manifest.feature_dim || "--";
  const sequenceCount = csv.sequence_count || manifest.sequence_count || 0;
  const csvFiles = csv.file_count || 0;

  setText("#rnn-manifest-status", manifest.exists ? `${manifest.sequence_count || 0} sequences` : "sequence_manifest.json not connected");
  setText("#rnn-source-status", source === "manifest" ? "sequence_manifest.json" : source === "csv" ? `${csvFiles} CSV feature file(s)` : "No sequence source");
  setText("#rnn-split-status", splitText);
  setText("#rnn-feature-columns-status", csv.feature_dim ? `${csv.feature_dim} CSV feature columns` : requirements.feature_dim ? `${featureDim} manifest feature dim` : "not parsed");
  setText("#rnn-target-status", (manifest.label_count || csv.label_count) ? `${manifest.label_count || csv.label_count} labeled sequence(s)` : "label / target missing");
  setText("#rnn-feature-dim-status", String(featureDim));
  setText("#rnn-readiness-status", canStart ? "Ready / CSV training enabled" : readiness.ready ? "Ready but CSV required for training" : "Not Ready");
  setText("#rnn-readiness-message", canStart
    ? "Sequence CSV is ready for RNN training. Full checks are available only for diagnostics."
    : readiness.message || "Sequence dataset still needs attention. Open full checks for diagnostics.");
  setText("#rnn-readiness-mode-badge", canStart ? "Training enabled" : "CSV required");
  setText("#rnn-sequence-dataset-message", canStart
    ? `${sequenceCount} sequence(s) detected from CSV. RNN training can start.`
    : `${sequenceCount} sequence(s) detected. CSV must include sequence id, target label/value, at least one feature column, train/val split, and enough rows for sequence_length.`);
  setText("#rnn-sequence-dataset-preview", source === "none" ? "sequence_id, timestep, feature_1, feature_2, target" : `source=${source}, feature_dim=${featureDim}, split=${splitText}`);
  updateRnnStartControls();

  const compactGrid = qs("#rnn-readiness-compact-grid");
  if (compactGrid) {
    const compactRows = [
      { label: "CSV", value: source === "csv" ? `${csvFiles} file(s)` : "Required", ok: source === "csv" },
      { label: "Features", value: csv.feature_dim ? `${csv.feature_dim} columns` : "--", ok: Boolean(csv.feature_dim) },
      { label: "Labels", value: csv.label_count ? `${csv.label_count} sequences` : "--", ok: Boolean(csv.label_count) },
      { label: "Split", value: splitText, ok: Boolean(requirements.train_val_split) },
      { label: "Window", value: `min ${csv.min_length || 0} / need ${readiness.sequence_length || 1}`, ok: Number(csv.min_length || 0) >= Number(readiness.sequence_length || 1) }
    ];
    compactGrid.innerHTML = compactRows.map((item) => `
      <div class="rnn-readiness-compact-item ${item.ok ? "success" : "danger"}">
        <span>${escapeHtml(item.label)}</span>
        <strong>${escapeHtml(item.value)}</strong>
      </div>
    `).join("");
  }
  const details = qs("#rnn-readiness-details");
  if (details) details.open = !canStart;

  const list = qs("#rnn-readiness-checks");
  if (list) {
    const requirementRows = [
      { label: "CSV source", ok: source === "csv", message: source === "csv" ? `${csvFiles} CSV file(s) detected.` : "Import CSV feature sequence files; manifest-only sources cannot start MVP training." },
      { label: "Feature columns", ok: Boolean(csv.feature_dim), message: csv.feature_dim ? `${csv.feature_dim} feature column(s) detected.` : "Configure at least one valid feature column." },
      { label: "Target labels", ok: Boolean(csv.label_count), message: csv.label_count ? `${csv.label_count} labeled sequence(s) detected.` : "CSV must include label/target values." },
      { label: "Train/Val split", ok: Boolean(requirements.train_val_split), message: splitText === "-- / -- / --" ? "CSV must include train and val split rows." : `Split counts: ${splitText}.` },
      { label: "Window length", ok: Number(csv.min_length || 0) >= Number(readiness.sequence_length || 1), message: `Minimum length ${csv.min_length || 0}; required ${readiness.sequence_length || 1}.` }
    ];
    const checks = [
      ...requirementRows.map((item) => ({
        label: item.label,
        status: item.ok ? "pass" : "fail",
        message: item.message
      })),
      ...(readiness.checks || [])
    ];
    list.innerHTML = checks.map((check) => {
      const statusClass = check.status === "pass" ? "success" : check.status === "warning" ? "warning" : "danger";
      return `<li class="rnn-readiness-item ${statusClass}">
        <strong>${escapeHtml(check.label || check.key)}</strong>
        <span>${escapeHtml(check.message || "")}</span>
      </li>`;
    }).join("");
  }
}

async function loadRnnEvaluation(options = {}) {
  if (!appState.currentProjectId) {
    trainingModeState.rnn.evaluationRuns = [];
    trainingModeState.rnn.evaluationMetrics = null;
    trainingModeState.rnn.evaluationArtifacts = [];
    trainingModeState.rnn.evaluationRunId = "";
    trainingModeState.rnn.evaluationRunMetrics = {};
    renderRnnEvaluation();
    return;
  }
  if (trainingModeState.rnn.evaluationLoading && !options.force) {
    renderRnnEvaluation();
    return;
  }
  if (!options.force && trainingModeState.rnn.evaluationRuns.length && trainingModeState.rnn.evaluationMetrics) {
    renderRnnEvaluation();
    return;
  }

  trainingModeState.rnn.evaluationLoading = true;
  renderRnnEvaluation();
  try {
    const runsPayload = await apiFetch(`/api/projects/${appState.currentProjectId}/train/runs`);
    const runs = (Array.isArray(runsPayload) ? runsPayload : []).filter(isSequenceEvaluationRun);
    trainingModeState.rnn.evaluationRuns = runs;

    const latestRun = runs[0] || null;
    if (!latestRun?.run_id) {
      trainingModeState.rnn.evaluationMetrics = null;
      trainingModeState.rnn.evaluationArtifacts = [];
      trainingModeState.rnn.evaluationRunId = "";
      trainingModeState.rnn.evaluationRunMetrics = {};
      return;
    }

    const runMetricEntries = await Promise.all(runs.map(async (run) => {
      try {
        const payload = await apiFetch(`/api/projects/${appState.currentProjectId}/train/runs/${encodeURIComponent(run.run_id)}/metrics`, { suppressToast: true });
        return [run.run_id, payload || null];
      } catch (err) {
        return [run.run_id, null];
      }
    }));
    const metricsByRun = Object.fromEntries(runMetricEntries.filter(([runId, payload]) => runId && payload));
    const metrics = metricsByRun[latestRun.run_id] || null;
    const [artifacts] = await Promise.all([
      apiFetch(`/api/projects/${appState.currentProjectId}/train/runs/${encodeURIComponent(latestRun.run_id)}/artifacts`)
    ]);
    trainingModeState.rnn.evaluationMetrics = metrics || null;
    trainingModeState.rnn.evaluationArtifacts = Array.isArray(artifacts) ? artifacts : [];
    trainingModeState.rnn.evaluationRunId = latestRun.run_id;
    trainingModeState.rnn.evaluationRunMetrics = metricsByRun;
  } catch (err) {
    eventBus.emit("toast", `RNN evaluation load failed: ${err.message}`);
    trainingModeState.rnn.evaluationMetrics = null;
    trainingModeState.rnn.evaluationArtifacts = [];
    trainingModeState.rnn.evaluationRunMetrics = {};
  } finally {
    trainingModeState.rnn.evaluationLoading = false;
    renderRnnEvaluation();
  }
}

function isSequenceEvaluationRun(run) {
  const architecture = String(run?.architecture || "").toLowerCase();
  const backend = String(run?.backend || "").toLowerCase();
  const taskType = String(run?.task_type || run?.task || "").toLowerCase();
  const model = String(run?.model || "").toLowerCase();
  return (
    architecture === "rnn" ||
    backend === "pytorch_lstm" ||
    backend === "sklearn_xgboost" ||
    taskType.includes("sequence") ||
    model.includes("xgboost")
  );
}

function renderRnnEvaluation() {
  const badge = qs("#rnn-eval-run-badge");
  const message = qs("#rnn-eval-message");
  if (!badge && !message) return;

  const runs = trainingModeState.rnn.evaluationRuns || [];
  const metrics = trainingModeState.rnn.evaluationMetrics || null;
  const artifacts = trainingModeState.rnn.evaluationArtifacts || [];
  const activeRun = runs.find((run) => run.run_id === trainingModeState.rnn.evaluationRunId) || runs[0] || null;
  const summary = activeRun || {};
  const bestMetrics = metrics?.best_metrics || summary.best_metrics || {};
  const history = Array.isArray(metrics?.history) ? metrics.history : [];
  const latestMetrics = history.length ? history[history.length - 1] : {};
  const metricSource = { ...latestMetrics, ...bestMetrics };
  const isRegression = String(metrics?.task_type || summary.task_type || "").toLowerCase().includes("regression") ||
    metricSource["val/mae"] !== undefined || metricSource["val/rmse"] !== undefined;

  if (badge) {
    const backend = sequenceBackendLabel(summary);
    badge.className = `summary-badge ${metrics ? "badge-success" : trainingModeState.rnn.evaluationLoading ? "badge-neutral" : "badge-warning"}`;
    badge.textContent = trainingModeState.rnn.evaluationLoading ? "Loading" : activeRun ? backend : "No run";
  }

  const primary = isRegression
    ? { label: "MAE", value: metricSource["val/mae"] ?? summary.primary_metric_value }
    : { label: "Accuracy", value: metricSource["val/accuracy"] ?? summary.best_accuracy };
  const secondary = isRegression
    ? { label: "RMSE", value: metricSource["val/rmse"] }
    : { label: "Macro-F1", value: metricSource["val/macro_f1"] ?? summary.primary_metric_value };

  setText("#rnn-eval-primary-label", primary.label);
  setText("#rnn-eval-primary-value", formatRnnMetric(primary.value));
  setText("#rnn-eval-secondary-label", secondary.label);
  setText("#rnn-eval-secondary-value", formatRnnMetric(secondary.value));
  setText("#rnn-eval-primary-history-label", primary.label);
  setText("#rnn-eval-secondary-history-label", secondary.label);
  setText("#rnn-eval-train-loss", formatRnnMetric(metricSource["train/loss"]));
  setText("#rnn-eval-val-loss", formatRnnMetric(metricSource["val/loss"]));

  if (message) {
    message.classList.toggle("hidden", Boolean(activeRun && !trainingModeState.rnn.evaluationLoading));
    message.textContent = trainingModeState.rnn.evaluationLoading
      ? "Loading sequence training metrics, artifacts, and run history..."
      : activeRun
        ? ""
        : "No RNN or XGBoost training run found for this project.";
  }

  renderRnnEvaluationEpochRows(history);
  renderRnnMetricTrendRows(history, isRegression, metrics || summary);
  renderRnnBaselineComparison(runs);
  renderRnnEvaluationArtifacts(artifacts, activeRun?.run_id || "");
  renderRnnEvaluationRunHistory(runs);
  renderRnnEvaluationSidebar({
    activeRun,
    metrics,
    artifacts,
    history,
    metricSource,
    isRegression,
    primary,
    secondary
  });
}

function renderRnnEvaluationEpochRows(history) {
  const tbody = qs("#rnn-eval-epoch-rows");
  if (!tbody) return;
  if (!Array.isArray(history) || !history.length) {
    tbody.innerHTML = `<tr><td colspan="6">No metric rows.</td></tr>`;
    return;
  }
  tbody.innerHTML = history.map((row, index) => {
    const accuracyOrMae = row["val/accuracy"] ?? row["val/mae"];
    const macroOrRmse = row["val/macro_f1"] ?? row["val/rmse"];
    return `<tr>
      <td><strong>${escapeHtml(row.epoch ?? index + 1)}</strong></td>
      <td><code>${formatRnnMetric(row["train/loss"])}</code></td>
      <td><code>${formatRnnMetric(row["val/loss"])}</code></td>
      <td>${formatRnnMetric(accuracyOrMae)}</td>
      <td>${formatRnnMetric(macroOrRmse)}</td>
      <td><span class="badge badge-success">Completed</span></td>
    </tr>`;
  }).join("");
}

function renderRnnEvaluationArtifacts(artifacts, runId) {
  const container = qs("#rnn-eval-sidebar-artifacts") || qs("#rnn-eval-artifact-list");
  if (!container) return;
  if (!Array.isArray(artifacts) || !artifacts.length || !runId) {
    container.textContent = "No artifacts.";
    return;
  }
  const priority = ["best.pt", "last.pt", "best.json", "last.json", "metrics.json", "results.csv", "run_summary.json", "feature_schema.json", "normalization_stats.json", "label_encoder.json", "model_metadata.json", "artifact_manifest.json"];
  const sorted = [...artifacts].sort((a, b) => {
    const ai = priority.indexOf(a.filename);
    const bi = priority.indexOf(b.filename);
    return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi) || String(a.filename).localeCompare(String(b.filename));
  });
  container.innerHTML = sorted.map((artifact) => {
    const filename = artifact.filename || "artifact";
    const relPath = artifact.rel_path || filename;
    const sizeKb = artifact.size !== undefined ? `${(Number(artifact.size) / 1024).toFixed(1)} KB` : "--";
    const url = `/api/projects/${appState.currentProjectId}/train/runs/${encodeURIComponent(runId)}/artifacts/download/${encodeURIComponent(filename)}?path=${encodeURIComponent(relPath)}`;
    return `<div class="rnn-result-item">
      <div>
        <strong>${escapeHtml(filename)}</strong>
        <span>${escapeHtml(relPath)} · ${escapeHtml(sizeKb)}</span>
      </div>
      <a class="btn btn-secondary btn-sm" href="${url}" target="_blank" download>Download</a>
    </div>`;
  }).join("");
}

function renderRnnMetricTrendRows(history, isRegression, metricContext = {}) {
  const container = qs("#rnn-eval-chart-stack");
  if (!container) return;
  const baselineNote = qs("#rnn-eval-baseline-note");
  const isSinglePointBaseline = isSinglePointBaselineRun(metricContext, history);
  baselineNote?.classList.toggle("hidden", !isSinglePointBaseline);
  if (!Array.isArray(history) || !history.length) {
    container.innerHTML = `<div class="rnn-eval-chart-empty">No metric trend loaded.</div>`;
    return;
  }
  const charts = isRegression
    ? [
      { label: "MAE", key: "val/mae" },
      { label: "RMSE", key: "val/rmse" },
      { label: "Train Loss", key: "train/loss" },
      { label: "Val Loss", key: "val/loss" }
    ]
    : [
      { label: "Accuracy", key: "val/accuracy" },
      { label: "Macro-F1", key: "val/macro_f1" },
      { label: "Train Loss", key: "train/loss" },
      { label: "Val Loss", key: "val/loss" }
    ];
  container.innerHTML = charts.map((chart) => {
    const values = metricSeries(history, chart.key);
    const latest = values.length ? values[values.length - 1] : null;
    const points = sparklinePoints(values);
    const empty = values.length < 1;
    return `<div class="rnn-eval-chart-row">
      <div class="rnn-eval-chart-label">
        <strong>${escapeHtml(chart.label)}</strong>
        <span>${isSinglePointBaseline ? "Single-point baseline" : "Latest"} ${formatRnnMetric(latest)}</span>
      </div>
      <div class="rnn-eval-sparkline ${empty ? "is-empty" : ""}">
        ${empty
          ? `<span>Not enough data</span>`
          : `<svg viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden="true"><polyline points="${escapeHtml(points)}"></polyline></svg>`}
      </div>
    </div>`;
  }).join("");
}

function isSinglePointBaselineRun(context = {}, history = []) {
  const backend = String(context.backend || "").toLowerCase();
  const model = String(context.model || "").toLowerCase();
  if (!(backend === "sklearn_xgboost" || model.includes("xgboost"))) return false;
  const metricKeys = ["val/accuracy", "val/macro_f1", "val/mae", "val/rmse"];
  return metricKeys.some((key) => metricSeries(history, key).length <= 1);
}

function renderRnnBaselineComparison(runs) {
  const container = qs("#rnn-eval-compare-chart");
  if (!container) return;
  const metricKey = trainingModeState.rnn.comparisonMetric || "macro_f1";
  qsa("[data-rnn-compare-metric]").forEach((button) => {
    button.classList.toggle("active", button.dataset.rnnCompareMetric === metricKey);
  });
  const metricConfig = getComparisonMetricConfig(metricKey);
  const completedRuns = (Array.isArray(runs) ? runs : []).filter((run) => String(run.status || "").toLowerCase() === "completed");
  if (!completedRuns.length) {
    container.innerHTML = `<div class="rnn-eval-chart-empty">No comparable runs loaded.</div>`;
    return;
  }
  const metricsByRun = trainingModeState.rnn.evaluationRunMetrics || {};
  const grouped = new Map();
  completedRuns.forEach((run) => {
    const key = normalizeRnnModelGroup(run);
    const metrics = metricsByRun[run.run_id] || {};
    const value = getRunComparisonMetric(run, metrics, metricConfig);
    if (!Number.isFinite(value)) return;
    const current = grouped.get(key);
    const better = !current || (metricConfig.lowerBetter ? value < current.value : value > current.value);
    if (better) grouped.set(key, { label: key, value, run, metricConfig });
  });
  const order = ["LSTM", "GRU", "BiLSTM", "XGBoost"];
  const rows = order.map((label) => grouped.get(label) || { label, value: null, metricConfig });
  const availableRows = rows.filter((row) => Number.isFinite(row.value));
  if (!availableRows.length) {
    container.innerHTML = `<div class="rnn-eval-chart-empty">No ${escapeHtml(metricConfig.label)} values loaded for completed runs.</div>`;
    return;
  }
  const values = availableRows.map((row) => row.value);
  const max = Math.max(...values, 0.000001);
  const min = Math.min(...values);
  container.innerHTML = rows.map((row) => {
    const hasValue = Number.isFinite(row.value);
    const percent = !hasValue
      ? 0
      : metricConfig.lowerBetter
        ? Math.max(4, ((max - row.value) / Math.max(max - min, 0.000001)) * 100)
        : Math.max(4, (row.value / max) * 100);
    return `<div class="rnn-compare-mini-row ${hasValue ? "" : "is-missing"}">
      <div class="rnn-compare-mini-label">
        <strong>${escapeHtml(row.label)}</strong>
        <span>${escapeHtml(metricConfig.hint)}</span>
      </div>
      <div class="rnn-compare-mini-track"><span style="width: ${percent.toFixed(1)}%;"></span></div>
      <code>${hasValue ? formatRnnMetric(row.value) : "--"}</code>
    </div>`;
  }).join("");
}

function getComparisonMetricConfig(metricKey) {
  const configs = {
    accuracy: { key: "val/accuracy", label: "Accuracy", hint: "higher better", lowerBetter: false, runFields: ["best_accuracy", "accuracy"] },
    macro_f1: { key: "val/macro_f1", label: "Macro-F1", hint: "higher better", lowerBetter: false, runFields: ["best_macro_f1", "macro_f1", "primary_metric_value"] },
    val_loss: { key: "val/loss", label: "Val Loss", hint: "lower better", lowerBetter: true, runFields: ["best_val_loss", "val_loss"] }
  };
  return configs[metricKey] || configs.macro_f1;
}

function normalizeRnnModelGroup(run = {}) {
  const model = String(run.model || "").toLowerCase();
  const runId = String(run.run_id || "").toLowerCase();
  const backend = String(run.backend || "").toLowerCase();
  const source = `${model} ${runId}`;
  if (source.includes("xgboost") || backend === "sklearn_xgboost") return "XGBoost";
  if (source.includes("bilstm") || run.bidirectional) return "BiLSTM";
  if (source.includes("gru")) return "GRU";
  return "LSTM";
}

function getRunComparisonMetric(run = {}, metrics = {}, metricConfig = getComparisonMetricConfig("macro_f1")) {
  const bestMetrics = metrics.best_metrics || {};
  const history = Array.isArray(metrics.history) ? metrics.history : [];
  const historyValues = metricSeries(history, metricConfig.key);
  if (historyValues.length) {
    return metricConfig.lowerBetter ? Math.min(...historyValues) : Math.max(...historyValues);
  }
  const direct = bestMetrics[metricConfig.key];
  if (direct !== undefined && direct !== null && direct !== "") return Number(direct);
  for (const field of metricConfig.runFields || []) {
    const value = run[field];
    if (value !== undefined && value !== null && value !== "") return Number(value);
  }
  return Number.NaN;
}

function metricSeries(history, key) {
  return history
    .map((row) => Number(row?.[key]))
    .filter((value) => Number.isFinite(value));
}

function sparklinePoints(values) {
  if (!values.length) return "";
  if (values.length === 1) return "0.00,16.00 100.00,16.00";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = Math.max(max - min, 0.000001);
  return values.map((value, index) => {
    const x = values.length === 1 ? 50 : (index / (values.length - 1)) * 100;
    const y = 28 - ((value - min) / spread) * 24;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ");
}

function renderRnnEvaluationSidebar({ activeRun, metrics, artifacts, history, metricSource, isRegression, primary, secondary }) {
  toggleRnnEvaluationRightPanel(trainingModeState.activeMode === "rnn" && trainingModeState.activeRnnPanel === "evaluation" && appState.currentPage === "training");
  const statusBadge = qs("#rnn-eval-sidebar-status");
  if (statusBadge) {
    statusBadge.className = `summary-badge ${activeRun ? "badge-success" : "badge-neutral"}`;
    statusBadge.textContent = activeRun ? activeRun.status || "loaded" : "No run";
  }

  const dataset = metrics?.dataset_summary || {};
  const readiness = trainingModeState.rnn.readiness?.summary?.csv || {};
  const splitCounts = dataset.split_counts || readiness.split_counts || {};
  const splitText = ["train", "val", "test"].map((key) => `${key}: ${splitCounts[key] ?? 0}`).join(" / ");
  const config = trainingModeState.rnn.config || {};
  const modelLabel = activeRun?.model || metrics?.model || sequenceBackendLabel(activeRun || metrics || {});
  const backendLabel = metrics?.backend || activeRun?.backend || "--";
  const taskLabel = isRegression ? "regression" : "classification";

  renderRnnSidebarRows("#rnn-eval-sidebar-run", [
    ["Run ID", activeRun?.run_id || "--", true],
    ["Model", modelLabel || "--"],
    ["Backend", backendLabel || "--", true],
    ["Status", activeRun?.status || "--"],
    ["Task", activeRun?.task_type || metrics?.task_type || taskLabel]
  ]);
  renderRnnSidebarRows("#rnn-eval-sidebar-dataset", [
    ["CSV files", String((dataset.csv_files || []).length || readiness.csv_files || 0)],
    ["Sequences", String(dataset.sequence_count ?? readiness.sequence_count ?? "--")],
    ["Feature dim", String(dataset.feature_dim ?? readiness.feature_dim ?? "--")],
    ["Split", splitText],
    ["Window", `length ${dataset.sequence_length ?? config.sequence_length ?? "--"} / stride ${dataset.stride ?? config.stride ?? "--"} / horizon ${config.horizon ?? "--"}`]
  ]);
  renderRnnSidebarRows("#rnn-eval-sidebar-metrics", [
    [primary.label, formatRnnMetric(primary.value)],
    [secondary.label, formatRnnMetric(secondary.value)],
    ["Val Loss", formatRnnMetric(metricSource?.["val/loss"])],
    ["Best epoch", String(metrics?.best_epoch ?? activeRun?.best_epoch ?? "--")]
  ]);
  renderRnnEvaluationArtifacts(artifacts, activeRun?.run_id || "");
}

function renderRnnSidebarRows(selector, rows) {
  const container = qs(selector);
  if (!container) return;
  container.innerHTML = rows.map(([label, value, isCode]) => {
    const safeValue = escapeHtml(value ?? "--");
    const valueHtml = isCode ? `<code>${safeValue}</code>` : `<span>${safeValue}</span>`;
    return `<div class="summary-row"><span>${escapeHtml(label)}</span>${valueHtml}</div>`;
  }).join("");
}

function renderRnnEvaluationRunHistory(runs) {
  const tbody = qs("#rnn-eval-run-history");
  if (!tbody) return;
  if (!Array.isArray(runs) || !runs.length) {
    tbody.innerHTML = `<tr><td colspan="6">No sequence runs.</td></tr>`;
    return;
  }
  tbody.innerHTML = runs.map((run) => {
    const primaryLabel = run.primary_metric_name || (String(run.task_type || "").includes("regression") ? "MAE" : "Macro-F1");
    const primaryValue = run.primary_metric_value ?? run.platform_score ?? run.best_macro_f1 ?? run.best_mae;
    return `<tr>
      <td><code>${escapeHtml(run.run_id || "--")}</code></td>
      <td>${escapeHtml(run.model || "--")}</td>
      <td>${escapeHtml(sequenceBackendLabel(run))}</td>
      <td>${escapeHtml(primaryLabel)} ${formatRnnMetric(primaryValue)}</td>
      <td><span class="badge ${run.status === "completed" ? "badge-success" : "badge-warning"}">${escapeHtml(run.status || "--")}</span></td>
      <td>${escapeHtml(formatRnnDate(run.completed_at || run.created_at || run.started_at))}</td>
    </tr>`;
  }).join("");
}

function sequenceBackendLabel(run = {}) {
  const backend = String(run.backend || "").toLowerCase();
  if (backend === "sklearn_xgboost") return "XGBoost";
  if (backend === "pytorch_lstm") return "LSTM / GRU";
  return run.backend || "Sequence";
}

function formatRnnMetric(value, digits = 3) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) return "--";
  return Number(value).toFixed(digits);
}

function formatRnnDate(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

async function loadRnnInferenceModels(options = {}) {
  if (!appState.currentProjectId || (trainingModeState.rnn.inferenceLoading && !options.force)) {
    renderRnnInferenceModels();
    return;
  }
  if (!options.force && trainingModeState.rnn.inferenceModels.length) {
    renderRnnInferenceModels();
    return;
  }

  trainingModeState.rnn.inferenceLoading = true;
  renderRnnInferenceModels();
  try {
    const models = await apiFetch(`/api/projects/${appState.currentProjectId}/models`);
    trainingModeState.rnn.inferenceModels = (Array.isArray(models) ? models : []).filter((model) =>
      model.architecture === "rnn" || model.backend === trainingModeState.rnn.backend
    );
  } catch (err) {
    trainingModeState.rnn.inferenceModels = [];
    eventBus.emit("toast", `Failed to load RNN models: ${err.message}`);
  } finally {
    trainingModeState.rnn.inferenceLoading = false;
    renderRnnInferenceModels();
  }
}

function renderRnnInferenceModels() {
  const select = qs("#rnn-inference-model");
  if (!select) return;
  const current = select.value;
  const models = trainingModeState.rnn.inferenceModels;
  if (trainingModeState.rnn.inferenceLoading) {
    select.innerHTML = `<option value="">Loading RNN models...</option>`;
  } else if (!models.length) {
    select.innerHTML = `<option value="">No RNN model found</option>`;
  } else {
    select.innerHTML = `<option value="">Select RNN model</option>${models.map((model) => {
      const label = `${model.run_id || "run"} / ${model.weight_type || "weight"} / ${model.model_name || "RNN"}`;
      return `<option value="${escapeHtml(model.model_id)}">${escapeHtml(label)}</option>`;
    }).join("")}`;
    const firstReady = models.find((model) => model.status === "ready");
    if (models.some((model) => model.model_id === current)) {
      select.value = current;
    } else {
      select.value = (firstReady || models[0])?.model_id || "";
    }
  }
  syncRnnInferencePathInput();
  updateRnnInferenceControls();
}

function updateRnnInferenceControls() {
  const btn = qs("#rnn-run-sequence-inference");
  const reason = qs("#rnn-inference-reason");
  if (!btn) return;
  syncRnnInferencePathInput();
  const message = getRnnInferenceBlockerMessage();
  const canRun = !message;
  btn.disabled = !canRun;
  btn.classList.toggle("btn-primary", canRun);
  btn.classList.toggle("btn-disabled", !canRun);
  if (reason) reason.textContent = message || "Ready to run CSV sequence inference.";
}

function syncRnnInferencePathInput() {
  const pathInput = qs("#rnn-inference-csv-path");
  if (!pathInput) return;
  const trusted = appState.systemHealth?.local_trusted_mode === true;
  pathInput.disabled = !trusted;
  if (!trusted) {
    pathInput.placeholder = "Local CSV path disabled (Trusted Local Mode off)";
    pathInput.value = "";
  } else {
    pathInput.placeholder = "Project CSV path, e.g. sequences/data.csv";
  }
}

function getRnnInferenceBlockerMessage() {
  if (!appState.currentProjectId) return "Open a project before sequence inference.";
  if (trainingModeState.rnn.inferenceLoading) return "Loading RNN models.";
  if (trainingModeState.rnn.inferenceRunning) return "Sequence inference is running.";
  if (!qs("#rnn-inference-model")?.value) return "Select an RNN model.";
  const hasFile = Boolean(qs("#rnn-inference-csv-file")?.files?.[0]);
  const trusted = appState.systemHealth?.local_trusted_mode === true;
  const hasPath = trusted && Boolean(qs("#rnn-inference-csv-path")?.value?.trim());
  if (!hasFile && !hasPath) {
    return trusted ? "Provide a CSV feature sequence file or project CSV path." : "Upload a CSV feature sequence file.";
  }
  return "";
}

async function runRnnSequenceInference(event) {
  event?.preventDefault();
  const blocker = getRnnInferenceBlockerMessage();
  if (blocker) {
    eventBus.emit("toast", blocker);
    updateRnnInferenceControls();
    return;
  }

  const form = new FormData();
  form.append("model_id", qs("#rnn-inference-model")?.value || "");
  form.append("device", qs("#rnn-inference-device")?.value || "gpu");
  const file = qs("#rnn-inference-csv-file")?.files?.[0];
  const csvPath = qs("#rnn-inference-csv-path")?.value?.trim();
  if (file) form.append("file", file);
  else if (csvPath) form.append("csv_path", csvPath);

  trainingModeState.rnn.inferenceRunning = true;
  updateRnnInferenceControls();
  try {
    const result = await apiFetch(`/api/projects/${appState.currentProjectId}/inference/sequence`, {
      method: "POST",
      body: form
    });
    trainingModeState.rnn.inferenceResult = result;
    appState.inferenceJobsProjectId = "";
    renderRnnInferenceResult();
    eventBus.emit("toast", "RNN sequence inference completed.");
  } catch (err) {
    eventBus.emit("toast", `RNN sequence inference failed: ${err.message}`);
  } finally {
    trainingModeState.rnn.inferenceRunning = false;
    updateRnnInferenceControls();
  }
}

function renderRnnInferenceResult() {
  const container = qs("#rnn-inference-result");
  const result = trainingModeState.rnn.inferenceResult;
  if (!container) return;
  if (!result) {
    container.textContent = "No sequence inference result yet.";
    return;
  }
  const summary = result.summary || {};
  const predictions = result.predictions || [];
  const firstRows = predictions.slice(0, 6).map((item) => {
    const confidence = item.confidence !== undefined ? ` (${Number(item.confidence).toFixed(3)})` : "";
    return `<li><code>${escapeHtml(item.sequence_id)}</code> -> <strong>${escapeHtml(item.prediction)}</strong>${confidence}</li>`;
  }).join("");
  container.innerHTML = `
    <div class="summary-row"><span>Job</span><code>${escapeHtml(result.job_id || "--")}</code></div>
    <div class="summary-row"><span>Sequences</span><code>${escapeHtml(summary.sequence_count ?? predictions.length)}</code></div>
    <div class="summary-row"><span>Latency</span><code>${escapeHtml(summary.inference_time_ms ?? "--")} ms</code></div>
    <ul class="rnn-inference-list">${firstRows || "<li>No predictions returned.</li>"}</ul>
    <div class="inline-actions">
      ${result.urls?.prediction_json ? `<a class="btn btn-secondary btn-sm" target="_blank" href="${escapeHtml(result.urls.prediction_json)}">prediction.json</a>` : ""}
      ${result.urls?.prediction_csv ? `<a class="btn btn-secondary btn-sm" target="_blank" href="${escapeHtml(result.urls.prediction_csv)}">predictions.csv</a>` : ""}
    </div>
  `;
}

async function loadRnnModelCatalog(options = {}) {
  if (!appState.currentProjectId) {
    trainingModeState.rnn.modelCatalog = getFallbackRnnModelCatalog();
    renderRnnModelSelector();
    return;
  }
  if (trainingModeState.rnn.modelCatalogLoading && !options.force) {
    renderRnnModelSelector();
    return;
  }
  if (trainingModeState.rnn.modelCatalog.length && !options.force) {
    renderRnnModelSelector();
    return;
  }

  trainingModeState.rnn.modelCatalogLoading = true;
  renderRnnModelSelector();
  try {
    const payload = await apiFetch(`/api/projects/${appState.currentProjectId}/models/catalog?architecture=rnn&usage=all`);
    const models = Array.isArray(payload.models) ? payload.models : [];
    trainingModeState.rnn.modelCatalog = models.length ? models : getFallbackRnnModelCatalog();
  } catch (err) {
    trainingModeState.rnn.modelCatalog = getFallbackRnnModelCatalog();
    eventBus.emit("toast", `RNN model catalog load failed: ${err.message}`);
  } finally {
    trainingModeState.rnn.modelCatalogLoading = false;
    renderRnnModelSelector();
  }
}

function getFallbackRnnModelCatalog() {
  return [
    { model_id: "fallback.rnn.lstm-classifier", display_name: "LSTM Classifier", backend: "pytorch_lstm", task_family: "sequence_classification", selector_value: "lstm", guide_key: "lstm_classification", trainable: true, training_enabled: true, status: "available" },
    { model_id: "fallback.rnn.lstm-regressor", display_name: "LSTM Regressor", backend: "pytorch_lstm", task_family: "sequence_regression", selector_value: "lstm", guide_key: "lstm_regression", trainable: true, training_enabled: true, status: "available" },
    { model_id: "fallback.rnn.gru-classifier", display_name: "GRU Classifier", backend: "pytorch_lstm", task_family: "sequence_classification", selector_value: "gru", guide_key: "gru_classification", trainable: true, training_enabled: true, status: "available" },
    { model_id: "fallback.rnn.gru-regressor", display_name: "GRU Regressor", backend: "pytorch_lstm", task_family: "sequence_regression", selector_value: "gru", guide_key: "gru_regression", trainable: true, training_enabled: true, status: "available" },
    { model_id: "fallback.rnn.bilstm-classifier", display_name: "BiLSTM Classifier", backend: "pytorch_lstm", task_family: "sequence_classification", selector_value: "bilstm", guide_key: "bilstm_classification", trainable: true, training_enabled: true, status: "available" },
    { model_id: "fallback.rnn.bilstm-regressor", display_name: "BiLSTM Regressor", backend: "pytorch_lstm", task_family: "sequence_regression", selector_value: "bilstm", guide_key: "bilstm_regression", trainable: true, training_enabled: true, status: "available" },
    { model_id: "fallback.rnn.fastrnn-classifier", display_name: "FastRNN Classifier", backend: "pytorch_fastrnn", task_family: "sequence_classification", selector_value: "fastrnn", guide_key: "fastrnn_classification", trainable: false, training_enabled: false, status: "planned" },
    { model_id: "fallback.rnn.fastrnn-regressor", display_name: "FastRNN Regressor", backend: "pytorch_fastrnn", task_family: "sequence_regression", selector_value: "fastrnn", guide_key: "fastrnn_regression", trainable: false, training_enabled: false, status: "planned" },
    { model_id: "fallback.xgboost.classifier", display_name: "XGBoost Classifier", backend: "sklearn_xgboost", task_family: "sequence_classification", selector_value: "xgboost_classifier", guide_key: "xgboost_classification", trainable: true, training_enabled: true, status: "available" },
    { model_id: "fallback.xgboost.regressor", display_name: "XGBoost Regressor", backend: "sklearn_xgboost", task_family: "sequence_regression", selector_value: "xgboost_regressor", guide_key: "xgboost_regression", trainable: true, training_enabled: true, status: "available" },
    { model_id: "fallback.isolation_forest.classifier", display_name: "Isolation Forest Baseline", backend: "sklearn_isolation_forest", task_family: "sequence_classification", selector_value: "isolation_forest", guide_key: "isolation_forest_classification", trainable: false, training_enabled: false, status: "planned" }
  ];
}

function getTrainableTemplateRnnCatalog() {
  const catalog = trainingModeState.rnn.modelCatalog.length ? trainingModeState.rnn.modelCatalog : getFallbackRnnModelCatalog();
  const templates = catalog.filter((model) => model.source !== "project_trained");
  return templates.length ? templates : getFallbackRnnModelCatalog();
}

function renderRnnModelSelector() {
  const select = qs("#rnn-model-family");
  if (!select) return;

  const taskFamily = getSelectedRnnTaskHead() === "regression" ? "sequence_regression" : "sequence_classification";
  const current = select.value;
  const models = getTrainableTemplateRnnCatalog().filter((model) => model.task_family === taskFamily);

  if (!models.length) {
    select.innerHTML = `<option value="">No compatible RNN model found</option>`;
    syncRnnModelSelection();
    return;
  }

  const groups = [
    ["pytorch_lstm", "RNN / Sequence"],
    ["pytorch_fastrnn", "RNN / Sequence · planned"],
    ["sklearn_xgboost", "Tabular Baseline"],
    ["sklearn_isolation_forest", "Anomaly Baseline · planned"]
  ];
  const loadingOption = trainingModeState.rnn.modelCatalogLoading
    ? `<option value="" disabled>Loading catalog in background...</option>`
    : "";
  select.innerHTML = loadingOption + groups.map(([backend, label]) => {
    const items = models.filter((model) => model.backend === backend);
    if (!items.length) return "";
    return `<optgroup label="${escapeHtml(label)}">${items.map((model) => {
      const suffix = model.training_enabled ? "" : " · planned";
      return `<option value="${escapeHtml(model.model_id)}">${escapeHtml(model.display_name || model.model_id)}${suffix}</option>`;
    }).join("")}</optgroup>`;
  }).join("");

  const values = models.map((model) => model.model_id);
  if (values.includes(current)) {
    select.value = current;
  } else {
    const firstTrainable = models.find((model) => model.training_enabled && model.trainable);
    select.value = (firstTrainable || models[0]).model_id;
  }
  syncRnnModelSelection();
  renderRnnModelGuide();
  updateRnnStartControls();
}

async function loadRnnModelGuides() {
  if (trainingModeState.rnn.modelGuides || trainingModeState.rnn.modelGuidesLoading) {
    renderRnnModelGuide();
    return;
  }
  trainingModeState.rnn.modelGuidesLoading = true;
  renderRnnModelGuide();
  try {
    const response = await fetch("/static/data/model_guide_catalog.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    trainingModeState.rnn.modelGuides = await response.json();
  } catch (err) {
    trainingModeState.rnn.modelGuides = {};
    eventBus.emit("toast", `Model guide load failed: ${err.message}`);
  } finally {
    trainingModeState.rnn.modelGuidesLoading = false;
    renderRnnModelGuide();
  }
}

function getSelectedRnnModel() {
  const entry = getSelectedRnnModelEntry();
  return entry?.selector_value || qs("#rnn-model-family")?.value || "lstm";
}

function getSelectedRnnModelEntry() {
  const value = qs("#rnn-model-family")?.value || "";
  const catalog = getTrainableTemplateRnnCatalog();
  return catalog.find((model) => model.model_id === value || model.selector_value === value) || null;
}

function getSelectedRnnBackend() {
  return getSelectedRnnModelEntry()?.backend || "pytorch_lstm";
}

function getSelectedRnnTaskHead() {
  return qs("#rnn-task-head")?.value || "classification";
}

function getRnnGuideKey() {
  const entry = getSelectedRnnModelEntry();
  if (entry?.guide_key) return entry.guide_key;
  const model = getSelectedRnnModel();
  const taskHead = getSelectedRnnTaskHead();
  if (model === "xgboost_classifier") return "xgboost_classification";
  if (model === "xgboost_regressor") return "xgboost_regression";
  return `${model}_${taskHead}`;
}

function isSelectedRnnModelTrainable() {
  const entry = getSelectedRnnModelEntry();
  if (entry) return Boolean(entry.trainable && entry.training_enabled);
  return ["lstm", "gru", "bilstm"].includes(getSelectedRnnModel());
}

function syncRnnModelSelection() {
  const entry = getSelectedRnnModelEntry();
  const model = getSelectedRnnModel();
  const taskHead = qs("#rnn-task-head");
  const backend = qs("#rnn-backend");
  const infoIcon = qs("#rnn-model-info-icon");
  if (model === "xgboost_classifier" && taskHead) taskHead.value = "classification";
  if (model === "xgboost_regressor" && taskHead) taskHead.value = "regression";
  if (backend) {
    const backendName = entry?.backend || (model.startsWith("xgboost") ? "sklearn_xgboost" : "pytorch_lstm");
    backend.value = entry?.training_enabled === false ? `${backendName} (planned)` : backendName;
  }
  if (infoIcon) {
    const tooltips = {
      lstm: "LSTM uses input/forget/output gates and is the default choice for general CSV sequence learning.",
      gru: "GRU has fewer gates than LSTM, often trains faster, and is useful when data is limited.",
      bilstm: "BiLSTM reads the window in both directions. Use it for offline sequence tasks, not streaming inference.",
      fastrnn: "FastRNN is planned as a lightweight recurrent option. It is visible for roadmap clarity but not trainable yet.",
      xgboost_classifier: "XGBoost Classifier is a strong tabular baseline for sequence-window features.",
      xgboost_regressor: "XGBoost Regressor is a strong tabular baseline for numeric sequence targets.",
      isolation_forest: "Isolation Forest is planned for anomaly-oriented sequence-window baselines and is not trainable yet."
    };
    infoIcon.dataset.tooltip = tooltips[model] || entry?.display_name || "Select a compatible sequence model.";
  }
}

function renderRnnModelGuide() {
  const container = qs("#rnn-model-guide");
  if (!container) return;
  if (trainingModeState.rnn.modelGuidesLoading) {
    container.innerHTML = `<div class="section-title"><h3>Model Guide</h3><span class="summary-badge badge-neutral">Loading</span></div><p>Loading model guide...</p>`;
    return;
  }
  const guide = trainingModeState.rnn.modelGuides?.[getRnnGuideKey()];
  if (!guide) {
    container.innerHTML = `<div class="section-title"><h3>Model Guide</h3><span class="summary-badge badge-warning">Missing</span></div><p>No guide found for this model/task combination.</p>`;
    return;
  }
  const statusClass = guide.status === "trainable" ? "badge-success" : "badge-warning";
  container.innerHTML = `
    <div class="section-title">
      <h3>${escapeHtml(guide.title)}</h3>
      <span class="summary-badge ${statusClass}">${escapeHtml(guide.status === "trainable" ? "Trainable" : "Planned")}</span>
    </div>
    <p>${escapeHtml(guide.summary)}</p>
    <div class="rnn-guide-grid">
      <div>
        <strong>適合</strong>
        <ul>${(guide.best_for || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      </div>
      <div>
        <strong>不適合</strong>
        <ul>${(guide.not_for || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      </div>
    </div>
    <div class="rnn-guide-note"><span>好結果通常長這樣</span><p>${escapeHtml(guide.good_result || "--")}</p></div>
    <div class="rnn-guide-note warning"><span>風險</span><p>${escapeHtml(guide.risk || "--")}</p></div>
  `;
}

function canStartRnnTraining() {
  const readiness = trainingModeState.rnn.readiness;
  const csv = readiness?.summary?.csv || {};
  const trainState = appState.trainingStatus || {};
  const isRunning = trainState.status === "training" || trainState.status === "stopping";
  return Boolean(
    appState.currentProjectId &&
    isSelectedRnnModelTrainable() &&
    readiness?.ready &&
    csv.valid &&
    Number(csv.file_count || 0) > 0 &&
    !trainingModeState.rnn.readinessLoading &&
    !trainingModeState.rnn.trainingStarting &&
    !isRunning
  );
}

function updateRnnStartControls() {
  const canStart = canStartRnnTraining();
  const message = getRnnStartBlockerMessage();
  const buttons = [qs("#rnn-start-disabled"), qs("#rnn-training-disabled-action")].filter(Boolean);
  buttons.forEach((button) => {
    button.disabled = !canStart;
    button.classList.toggle("btn-primary", canStart);
    button.classList.toggle("btn-disabled", !canStart);
    button.title = canStart ? "Start RNN training" : message;
  });

  const bannerBtn = qs("#rnn-start-disabled");
  if (bannerBtn) {
    bannerBtn.innerHTML = canStart
      ? `<i class="fa-solid fa-play"></i> Start RNN`
      : `<i class="fa-solid fa-lock"></i> Start RNN Disabled`;
  }
  const trainingBtn = qs("#rnn-training-disabled-action");
  if (trainingBtn) {
    trainingBtn.textContent = canStart ? "Start RNN Training" : message;
  }
  const stateBadge = qs("#rnn-training-state-badge");
  if (stateBadge) {
    stateBadge.className = `summary-badge ${canStart ? "badge-success" : "badge-warning"}`;
    stateBadge.textContent = canStart ? "Training enabled" : isSelectedRnnModelTrainable() ? "Readiness required" : "Backend planned";
  }
}

function preferGpuDevice(selector) {
  const select = qs(selector);
  if (!select) return;
  const hasGpuOption = Array.from(select.options || []).some((option) => option.value === "gpu");
  if (hasGpuOption && !select.value) select.value = "gpu";
}

function getRnnStartBlockerMessage() {
  if (!appState.currentProjectId) return "Open a project before starting RNN training.";
  if (trainingModeState.rnn.readinessLoading) return "RNN readiness is still checking.";
  if (trainingModeState.rnn.trainingStarting) return "RNN training is starting.";
  const trainState = appState.trainingStatus || {};
  if (trainState.status === "training" || trainState.status === "stopping") return "Another training job is already active.";
  if (!isSelectedRnnModelTrainable()) {
    const entry = getSelectedRnnModelEntry();
    return `${entry?.display_name || "Selected model"} is available in the catalog, but its training backend is not enabled yet.`;
  }
  const readiness = trainingModeState.rnn.readiness;
  if (!readiness) return "Run RNN readiness check before starting training.";
  const csv = readiness.summary?.csv || {};
  if (!csv.valid || Number(csv.file_count || 0) === 0) {
    return "RNNBackend MVP requires ready CSV feature sequence files under project/sequences.";
  }
  if (!readiness.ready) return readiness.message || "RNN readiness is not ready.";
  return "RNN training is disabled until readiness passes.";
}

async function startRnnTraining(event) {
  event?.preventDefault();
  if (!canStartRnnTraining()) {
    eventBus.emit("toast", getRnnStartBlockerMessage());
    return;
  }

  trainingModeState.rnn.trainingStarting = true;
  updateRnnStartControls();
  syncRnnModelSelection();
  const model = getSelectedRnnModel();
  const taskHead = getSelectedRnnTaskHead();
  const configData = {
    backend: getSelectedRnnBackend(),
    model,
    epochs: Number(qs("#rnn-epochs")?.value || 10),
    batch_size: Number(qs("#rnn-batch-size")?.value || 16),
    imgsz: 320,
    lr0: 0.001,
    device: qs("#rnn-device")?.value || "gpu",
    sequence_length: Number(qs("#rnn-sequence-length")?.value || 16),
    stride: Number(qs("#rnn-stride")?.value || 8),
    horizon: Number(qs("#rnn-horizon")?.value || 1),
    task_head: taskHead,
    hidden_size: Number(qs("#rnn-hidden-size")?.value || 128),
    num_layers: Number(qs("#rnn-layers")?.value || 2),
    dropout: Number(qs("#rnn-dropout")?.value || 0.2),
    bidirectional: model === "bilstm",
    gradient_clip_norm: Number(qs("#rnn-gradient-clip")?.value || 0),
    early_stopping_patience: Number(qs("#rnn-early-stopping-patience")?.value || 0)
  };

  try {
    await apiFetch(`/api/projects/${appState.currentProjectId}/train/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(configData)
    });
    eventBus.emit("toast", "RNN training started.");
    eventBus.emit("start-training-monitor");
    eventBus.emit("refresh-project");
  } catch (err) {
    eventBus.emit("toast", `RNN training failed to start: ${err.message}`);
  } finally {
    trainingModeState.rnn.trainingStarting = false;
    updateRnnStartControls();
  }
}

