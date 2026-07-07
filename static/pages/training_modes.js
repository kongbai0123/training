import { eventBus } from "../event_bus.js";
import { appState } from "../state.js";
import { apiFetch } from "../api.js";
import { qs, qsa, escapeHtml, setText } from "../utils.js";
import {
  formatSequenceMetric,
  sequenceBackendDisplayLabel
} from "./rnn_metric_helpers.js";
import {
  buildRnnEvaluationEpochRows,
  buildRnnEvaluationRunHistoryRows,
  buildRnnMetricTrendRows,
  buildRnnEvaluationSidebarViewModel,
  buildRnnBaselineComparisonViewModel,
  isSequenceEvaluationRun,
  resolveRnnEvaluationViewModel
} from "./rnn_evaluation_helpers.js";
import {
  renderRnnEvaluationArtifactList,
  renderRnnEvaluationEpochTableRows,
  renderRnnEvaluationRunHistoryTableRows,
  renderRnnEvaluationSidebarRows,
  renderRnnBaselineComparisonChart,
  renderRnnMetricTrendChartStack,
  resolveRnnEvaluationMessage,
  resolveRnnEvaluationRunBadge
} from "./rnn_evaluation_render_helpers.js";
import {
  renderRnnFeatureChipList,
  renderRnnPreviewContent,
  resolveRnnConfigMismatchRender,
  resolveRnnWindowSummaryRender
} from "./rnn_config_render_helpers.js";
import {
  RNN_MODEL_TOOLTIPS,
  fallbackRnnModelCatalog,
  isRnnModelTrainable,
  resolveRnnGuideKey,
  resolveRnnModelEntry,
  selectedRnnBackend,
  selectedRnnBackendDisplay,
  selectedRnnModelValue,
  trainableTemplateRnnCatalog
} from "./rnn_model_catalog_helpers.js";
import {
  renderRnnModelGuideContent,
  renderRnnModelSelectorOptions
} from "./rnn_model_render_helpers.js";
import {
  filterRnnInferenceModels,
  resolveRnnInferenceModelValue,
  rnnInferenceBlockerMessage
} from "./rnn_inference_helpers.js";
import {
  renderRnnInferenceModelOptions,
  renderRnnInferenceResultPanel,
  resolveRnnInferenceControlRender
} from "./rnn_inference_render_helpers.js";
import {
  buildRnnDatasetBadge,
  buildRnnFeatureChipModels,
  buildRnnMismatchSummary,
  buildRnnPreviewTableModel,
  buildRnnWindowSummaryRows,
  formatRnnFeatureConfigHash,
  resolveRnnFeatureDimension,
  resolveRnnWindowSummary
} from "./rnn_config_view_helpers.js";
import {
  canStartRnnTrainingFromState,
  parseRnnFeatureColumns,
  rnnStartBlockerMessage,
  summarizeRnnReadiness
} from "./rnn_readiness_helpers.js";
import {
  buildRnnReadinessCheckRows,
  renderRnnReadinessCheckList,
  renderRnnReadinessCompactGrid,
  renderRnnStartBannerButtonContent,
  resolveRnnReadinessBadge,
  resolveRnnReadinessEmptyView,
  resolveRnnReadinessSummaryView,
  resolveRnnTrainingActionText,
  resolveRnnTrainingStateBadge
} from "./rnn_readiness_render_helpers.js";
import { buildRnnArtifactListViewModel } from "./rnn_artifact_helpers.js";
import { buildRnnTrainingPayload } from "./rnn_training_payload_helpers.js";
import { trainingModeState } from "./training_mode_state.js";

export { trainingModeState } from "./training_mode_state.js";

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
  return parseRnnFeatureColumns(qs("#rnn-feature-columns")?.value || "");
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
  const datasetBadge = buildRnnDatasetBadge({
    files,
    datasetImporting: trainingModeState.rnn.datasetImporting
  });
  const badge = qs("#rnn-dataset-badge");
  if (badge) {
    badge.className = `summary-badge ${datasetBadge.badgeClass}`;
    badge.textContent = datasetBadge.label;
  }
  const featureDimInput = qs("#rnn-feature-dim");
  if (featureDimInput) featureDimInput.value = String(resolveRnnFeatureDimension({ config, inspection }));
  setText("#rnn-config-hash-badge", formatRnnFeatureConfigHash(config));
  const preview = qs("#rnn-sequence-dataset-preview");
  if (preview) {
    const previewModel = buildRnnPreviewTableModel({
      headers,
      rows: inspection.preview_rows
    });
    preview.innerHTML = renderRnnPreviewContent(previewModel);
  }
  renderRnnFeatureChips(validation);
  renderRnnWindowSummary(validation);
  renderRnnConfigMismatch();
  renderRnnModelGuide();
}

function renderRnnWindowSummary(validation = null) {
  const windowSummary = resolveRnnWindowSummary({
    validation,
    windowSummary: trainingModeState.rnn.windowSummary,
    configValidation: trainingModeState.rnn.configValidation
  });
  const viewModel = buildRnnWindowSummaryRows(windowSummary);
  const badge = qs("#rnn-window-status-badge");
  const warning = qs("#rnn-window-warning");
  const summary = qs("#rnn-window-summary");
  const renderView = resolveRnnWindowSummaryRender(viewModel);
  if (badge) {
    badge.className = renderView.badgeClassName;
    badge.textContent = renderView.badgeLabel;
  }
  if (summary) {
    summary.innerHTML = renderView.summaryHtml;
  }
  if (warning) {
    warning.classList.toggle("hidden", renderView.warningHidden);
    warning.innerHTML = renderView.warningHtml;
  }
}

function renderRnnFeatureChips(validation = null) {
  const list = qs("#rnn-feature-chip-list");
  if (!list) return;
  const chips = buildRnnFeatureChipModels({
    features: parseRnnFeatureInput(),
    headers: trainingModeState.rnn.configInspection?.headers,
    validation
  });
  list.innerHTML = renderRnnFeatureChipList(chips);
}

function renderRnnConfigMismatch() {
  const box = qs("#rnn-config-mismatch-warning");
  if (!box) return;
  const mismatchSummary = buildRnnMismatchSummary(trainingModeState.rnn.configMismatches);
  const renderView = resolveRnnConfigMismatchRender(mismatchSummary);
  box.classList.toggle("hidden", renderView.hidden);
  box.innerHTML = renderView.html;
}

function renderRnnReadiness() {
  const readiness = trainingModeState.rnn.readiness;
  const loading = trainingModeState.rnn.readinessLoading;
  const canStart = canStartRnnTraining();
  const badge = qs("#rnn-readiness-badge");
  if (badge) {
    const badgeView = resolveRnnReadinessBadge({ canStart, loading, readiness });
    badge.className = badgeView.className;
    badge.textContent = badgeView.text;
  }

  if (!readiness) {
    const emptyView = resolveRnnReadinessEmptyView(loading);
    setText("#rnn-readiness-status", emptyView.status);
    setText("#rnn-readiness-message", emptyView.message);
    const compactGrid = qs("#rnn-readiness-compact-grid");
    if (compactGrid) compactGrid.innerHTML = "";
    const list = qs("#rnn-readiness-checks");
    if (list) list.innerHTML = "";
    const details = qs("#rnn-readiness-details");
    if (details) details.open = false;
    updateRnnStartControls();
    return;
  }

  const {
    manifest,
    csv,
    requirements,
    source,
    splitText,
    featureDim,
    sequenceCount,
    csvFiles,
    compactRows,
    requirementRows
  } = summarizeRnnReadiness(readiness);

  setText("#rnn-manifest-status", manifest.exists ? `${manifest.sequence_count || 0} sequences` : "sequence_manifest.json not connected");
  setText("#rnn-source-status", source === "manifest" ? "sequence_manifest.json" : source === "csv" ? `${csvFiles} CSV feature file(s)` : "No sequence source");
  setText("#rnn-split-status", splitText);
  setText("#rnn-feature-columns-status", csv.feature_dim ? `${csv.feature_dim} CSV feature columns` : requirements.feature_dim ? `${featureDim} manifest feature dim` : "not parsed");
  setText("#rnn-target-status", (manifest.label_count || csv.label_count) ? `${manifest.label_count || csv.label_count} labeled sequence(s)` : "label / target missing");
  setText("#rnn-feature-dim-status", String(featureDim));
  const summaryView = resolveRnnReadinessSummaryView({
    canStart,
    readiness,
    sequenceCount,
    source,
    featureDim,
    splitText
  });
  setText("#rnn-readiness-status", summaryView.status);
  setText("#rnn-readiness-message", summaryView.message);
  setText("#rnn-readiness-mode-badge", summaryView.modeBadge);
  setText("#rnn-sequence-dataset-message", summaryView.datasetMessage);
  setText("#rnn-sequence-dataset-preview", summaryView.datasetPreview);
  updateRnnStartControls();

  const compactGrid = qs("#rnn-readiness-compact-grid");
  if (compactGrid) {
    compactGrid.innerHTML = renderRnnReadinessCompactGrid(compactRows);
  }
  const details = qs("#rnn-readiness-details");
  if (details) details.open = !canStart;

  const list = qs("#rnn-readiness-checks");
  if (list) {
    const checks = buildRnnReadinessCheckRows(requirementRows, readiness.checks);
    list.innerHTML = renderRnnReadinessCheckList(checks);
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

function renderRnnEvaluation() {
  const badge = qs("#rnn-eval-run-badge");
  const message = qs("#rnn-eval-message");
  if (!badge && !message) return;

  const runs = trainingModeState.rnn.evaluationRuns || [];
  const metrics = trainingModeState.rnn.evaluationMetrics || null;
  const artifacts = trainingModeState.rnn.evaluationArtifacts || [];
  const {
    activeRun,
    summary,
    history,
    metricSource,
    isRegression,
    primary,
    secondary
  } = resolveRnnEvaluationViewModel({
    runs,
    metrics,
    selectedRunId: trainingModeState.rnn.evaluationRunId
  });

  if (badge) {
    const badgeView = resolveRnnEvaluationRunBadge({
      hasMetrics: Boolean(metrics),
      loading: trainingModeState.rnn.evaluationLoading,
      activeRun,
      backend: sequenceBackendLabel(summary)
    });
    badge.className = badgeView.className;
    badge.textContent = badgeView.text;
  }

  setText("#rnn-eval-primary-label", primary.label);
  setText("#rnn-eval-primary-value", formatRnnMetric(primary.value));
  setText("#rnn-eval-secondary-label", secondary.label);
  setText("#rnn-eval-secondary-value", formatRnnMetric(secondary.value));
  setText("#rnn-eval-primary-history-label", primary.label);
  setText("#rnn-eval-secondary-history-label", secondary.label);
  setText("#rnn-eval-train-loss", formatRnnMetric(metricSource["train/loss"]));
  setText("#rnn-eval-val-loss", formatRnnMetric(metricSource["val/loss"]));

  if (message) {
    const messageView = resolveRnnEvaluationMessage({
      loading: trainingModeState.rnn.evaluationLoading,
      activeRun
    });
    message.classList.toggle("hidden", messageView.hidden);
    message.textContent = messageView.text;
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
  const epochRows = buildRnnEvaluationEpochRows(history);
  tbody.innerHTML = renderRnnEvaluationEpochTableRows(epochRows);
}

function renderRnnEvaluationArtifacts(artifacts, runId) {
  const container = qs("#rnn-eval-sidebar-artifacts") || qs("#rnn-eval-artifact-list");
  if (!container) return;
  const artifactList = buildRnnArtifactListViewModel({
    artifacts,
    projectId: appState.currentProjectId,
    runId
  });
  container.innerHTML = renderRnnEvaluationArtifactList(artifactList);
}

function renderRnnMetricTrendRows(history, isRegression, metricContext = {}) {
  const container = qs("#rnn-eval-chart-stack");
  if (!container) return;
  const baselineNote = qs("#rnn-eval-baseline-note");
  const trendRows = buildRnnMetricTrendRows({ history, isRegression, metricContext });
  baselineNote?.classList.toggle("hidden", !trendRows.isSinglePointBaseline);
  container.innerHTML = renderRnnMetricTrendChartStack(trendRows);
}

function renderRnnBaselineComparison(runs) {
  const container = qs("#rnn-eval-compare-chart");
  if (!container) return;
  const metricKey = trainingModeState.rnn.comparisonMetric || "macro_f1";
  qsa("[data-rnn-compare-metric]").forEach((button) => {
    button.classList.toggle("active", button.dataset.rnnCompareMetric === metricKey);
  });
  const metricsByRun = trainingModeState.rnn.evaluationRunMetrics || {};
  const comparison = buildRnnBaselineComparisonViewModel({
    runs,
    metricsByRun,
    metricKey
  });
  container.innerHTML = renderRnnBaselineComparisonChart(comparison);
}

function renderRnnEvaluationSidebar({ activeRun, metrics, artifacts, history, metricSource, isRegression, primary, secondary }) {
  toggleRnnEvaluationRightPanel(trainingModeState.activeMode === "rnn" && trainingModeState.activeRnnPanel === "evaluation" && appState.currentPage === "training");
  const sidebar = buildRnnEvaluationSidebarViewModel({
    activeRun,
    metrics,
    readiness: trainingModeState.rnn.readiness?.summary?.csv || {},
    config: trainingModeState.rnn.config || {},
    metricSource,
    isRegression,
    primary,
    secondary
  });
  const statusBadge = qs(sidebar.statusSelector);
  if (statusBadge) {
    statusBadge.className = sidebar.status.className;
    statusBadge.textContent = sidebar.status.text;
  }

  sidebar.rowSections.forEach((section) => renderRnnSidebarRows(section.selector, section.rows));
  renderRnnEvaluationArtifacts(artifacts, sidebar.artifactRunId);
}

function renderRnnSidebarRows(selector, rows) {
  const container = qs(selector);
  if (!container) return;
  container.innerHTML = renderRnnEvaluationSidebarRows(rows);
}

function renderRnnEvaluationRunHistory(runs) {
  const tbody = qs("#rnn-eval-run-history");
  if (!tbody) return;
  const runRows = buildRnnEvaluationRunHistoryRows(runs);
  tbody.innerHTML = renderRnnEvaluationRunHistoryTableRows(runRows);
}

function sequenceBackendLabel(run = {}) {
  return sequenceBackendDisplayLabel(run);
}

function formatRnnMetric(value, digits = 3) {
  return formatSequenceMetric(value, digits);
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
    trainingModeState.rnn.inferenceModels = filterRnnInferenceModels(models, trainingModeState.rnn.backend);
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
  select.innerHTML = renderRnnInferenceModelOptions({
    loading: trainingModeState.rnn.inferenceLoading,
    models
  });
  if (!trainingModeState.rnn.inferenceLoading && models.length) {
    select.value = resolveRnnInferenceModelValue(models, current);
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
  const renderView = resolveRnnInferenceControlRender(message);
  btn.disabled = renderView.disabled;
  btn.classList.toggle("btn-primary", renderView.primaryActive);
  btn.classList.toggle("btn-disabled", renderView.disabledActive);
  if (reason) reason.textContent = renderView.reasonText;
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
  const hasFile = Boolean(qs("#rnn-inference-csv-file")?.files?.[0]);
  const trusted = appState.systemHealth?.local_trusted_mode === true;
  const hasPath = trusted && Boolean(qs("#rnn-inference-csv-path")?.value?.trim());
  return rnnInferenceBlockerMessage({
    hasProject: Boolean(appState.currentProjectId),
    isLoading: trainingModeState.rnn.inferenceLoading,
    isRunning: trainingModeState.rnn.inferenceRunning,
    selectedModel: qs("#rnn-inference-model")?.value || "",
    hasFile,
    trusted,
    hasPath
  });
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
  container.innerHTML = renderRnnInferenceResultPanel(result);
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
  return fallbackRnnModelCatalog();
}

function getTrainableTemplateRnnCatalog() {
  return trainableTemplateRnnCatalog(trainingModeState.rnn.modelCatalog);
}

function renderRnnModelSelector() {
  const select = qs("#rnn-model-family");
  if (!select) return;

  const taskFamily = getSelectedRnnTaskHead() === "regression" ? "sequence_regression" : "sequence_classification";
  const current = select.value;
  const models = getTrainableTemplateRnnCatalog().filter((model) => model.task_family === taskFamily);

  select.innerHTML = renderRnnModelSelectorOptions({
    loading: trainingModeState.rnn.modelCatalogLoading,
    models
  });

  if (!models.length) {
    syncRnnModelSelection();
    return;
  }

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
  return selectedRnnModelValue(entry, qs("#rnn-model-family")?.value || "");
}

function getSelectedRnnModelEntry() {
  const value = qs("#rnn-model-family")?.value || "";
  return resolveRnnModelEntry(getTrainableTemplateRnnCatalog(), value);
}

function getSelectedRnnBackend() {
  return selectedRnnBackend(getSelectedRnnModelEntry(), getSelectedRnnModel());
}

function getSelectedRnnTaskHead() {
  return qs("#rnn-task-head")?.value || "classification";
}

function getRnnGuideKey() {
  const entry = getSelectedRnnModelEntry();
  return resolveRnnGuideKey(entry, getSelectedRnnModel(), getSelectedRnnTaskHead());
}

function isSelectedRnnModelTrainable() {
  return isRnnModelTrainable(getSelectedRnnModelEntry(), getSelectedRnnModel());
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
    backend.value = selectedRnnBackendDisplay(entry, model);
  }
  if (infoIcon) {
    infoIcon.dataset.tooltip = RNN_MODEL_TOOLTIPS[model] || entry?.display_name || "Select a compatible sequence model.";
  }
}

function renderRnnModelGuide() {
  const container = qs("#rnn-model-guide");
  if (!container) return;
  const guide = trainingModeState.rnn.modelGuides?.[getRnnGuideKey()];
  container.innerHTML = renderRnnModelGuideContent({
    loading: trainingModeState.rnn.modelGuidesLoading,
    guide
  });
}

function canStartRnnTraining() {
  return canStartRnnTrainingFromState({
    hasProject: Boolean(appState.currentProjectId),
    modelTrainable: isSelectedRnnModelTrainable(),
    readiness: trainingModeState.rnn.readiness,
    readinessLoading: trainingModeState.rnn.readinessLoading,
    trainingStarting: trainingModeState.rnn.trainingStarting,
    trainingStatus: appState.trainingStatus?.status || ""
  });
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
    bannerBtn.innerHTML = renderRnnStartBannerButtonContent(canStart);
  }
  const trainingBtn = qs("#rnn-training-disabled-action");
  if (trainingBtn) {
    trainingBtn.textContent = resolveRnnTrainingActionText({ canStart, message });
  }
  const stateBadge = qs("#rnn-training-state-badge");
  if (stateBadge) {
    const stateBadgeView = resolveRnnTrainingStateBadge({
      canStart,
      modelTrainable: isSelectedRnnModelTrainable()
    });
    stateBadge.className = stateBadgeView.className;
    stateBadge.textContent = stateBadgeView.text;
  }
}

function preferGpuDevice(selector) {
  const select = qs(selector);
  if (!select) return;
  const hasGpuOption = Array.from(select.options || []).some((option) => option.value === "gpu");
  if (hasGpuOption && !select.value) select.value = "gpu";
}

function getRnnStartBlockerMessage() {
  return rnnStartBlockerMessage({
    hasProject: Boolean(appState.currentProjectId),
    readinessLoading: trainingModeState.rnn.readinessLoading,
    trainingStarting: trainingModeState.rnn.trainingStarting,
    trainingStatus: appState.trainingStatus?.status || "",
    modelTrainable: isSelectedRnnModelTrainable(),
    modelLabel: getSelectedRnnModelEntry()?.display_name || "Selected model",
    readiness: trainingModeState.rnn.readiness
  });
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
  const configData = buildRnnTrainingPayload({
    backend: getSelectedRnnBackend(),
    model,
    taskHead,
    formValues: collectRnnTrainingFormValues()
  });

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

function collectRnnTrainingFormValues() {
  return {
    epochs: qs("#rnn-epochs")?.value,
    batchSize: qs("#rnn-batch-size")?.value,
    device: qs("#rnn-device")?.value,
    sequenceLength: qs("#rnn-sequence-length")?.value,
    stride: qs("#rnn-stride")?.value,
    horizon: qs("#rnn-horizon")?.value,
    hiddenSize: qs("#rnn-hidden-size")?.value,
    layers: qs("#rnn-layers")?.value,
    dropout: qs("#rnn-dropout")?.value,
    gradientClipNorm: qs("#rnn-gradient-clip")?.value,
    earlyStoppingPatience: qs("#rnn-early-stopping-patience")?.value
  };
}

