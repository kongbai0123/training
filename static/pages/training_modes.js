import { eventBus } from "../event_bus.js";
import { appState, t } from "../state.js";
import { apiFetch, apiUpload } from "../api.js";
import { beginTask, followServerTask } from "../core/task_progress.js";
import { qs, qsa, escapeHtml, setHTML, setText } from "../utils.js";
import { renderTrainingFlowGuide } from "../core/training_flow_guide.js";
import {
  formatSequenceMetric,
  sequenceBackendDisplayLabel
} from "./rnn_metric_helpers.js";
import {
  buildRnnEvaluationEpochRows,
  buildRnnEvaluationRunHistoryRows,
  buildRnnMetricTrendRows,
  buildRnnTaskAwareDashboard,
  buildRnnEvaluationSidebarViewModel,
  buildRnnBaselineComparisonViewModel,
  isSequenceEvaluationRun,
  resolveRnnEvaluationViewModel
} from "./rnn_evaluation_helpers.js?v=20260708-rnn-epoch-axis";
import {
  renderRnnEvaluationRunSelectorOptions,
  renderRnnEvaluationArtifactList,
  renderRnnEvaluationEpochTableRows,
  renderRnnEvaluationRunHistoryTableRows,
  renderRnnEvaluationSidebarRows,
  renderRnnMetricTrendChartStack,
  renderRnnTaskDiagnostic,
  resolveRnnEvaluationOverviewRender,
  resolveRnnEvaluationSidebarStatusRender
} from "./rnn_evaluation_render_helpers.js?v=20260708-rnn-active-run";
import {
  renderRnnPreviewContent,
  resolveRnnConfigMismatchRender,
  resolveRnnWindowSummaryRender
} from "./rnn_config_render_helpers.js";
import { renderExportArtifactList } from "./export.js";
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
  resolveRnnTrainingStateBadge
} from "./rnn_readiness_render_helpers.js";
import { buildRnnArtifactListViewModel } from "./rnn_artifact_helpers.js";
import { buildRnnTrainingPayload } from "./rnn_training_payload_helpers.js";
import {
  buildRnnBarChartSvg,
  buildRnnDiagnosticSvg,
  buildRnnLineChartSvg,
  buildRnnLiveMonitorViewModel,
  buildRnnSmartAssessment
} from "./rnn_intelligence_helpers.js";
import { trainingModeState } from "./training_mode_state.js";

export { trainingModeState } from "./training_mode_state.js";

let rnnScoreChart = null;
let rnnLossChart = null;
let rnnRunComparisonCharts = [];
let rnnMonitorQualityChart = null;
let rnnMonitorLossChart = null;
const rnnMonitorChartSignatures = new Map();
let currentRnnEvaluationDashboard = null;
let currentRnnComparisons = [];
let trainingModeSidebarInitialized = false;

export function initTrainingModeSidebar() {
  if (trainingModeSidebarInitialized) return;
  trainingModeSidebarInitialized = true;
  qsa("[data-training-mode]").forEach((button) => {
    button.addEventListener("click", () => setTrainingMode(button.dataset.trainingMode));
  });

  qsa("[data-rnn-nav]").forEach((button) => {
    button.addEventListener("click", () => {
      if (isHiddenModeNavButton(button)) return;
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
      loadRnnConfig();
      if (trainingModeState.activeRnnPanel === "sequence-test") {
        loadRnnInferenceModels();
        loadLatestRnnInferenceResult();
      }
      if (trainingModeState.activeRnnPanel === "evaluation") loadRnnEvaluation();
      if (trainingModeState.activeRnnPanel === "export") loadRnnExportModels();
    });
  });

  qsa("[data-cnn-nav]").forEach((button) => {
    button.addEventListener("click", () => {
      if (isHiddenModeNavButton(button)) return;
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
        if (trainingModeState.activeMode === "rnn") loadRnnConfig();
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
  eventBus.on("language-changed", () => {
    syncRnnModelSelection();
    renderTrainingWorkspace();
    renderRnnEvaluation();
  });
  eventBus.on("refresh-project", () => {
    trainingModeState.rnn.evaluationRequestSeq += 1;
    trainingModeState.rnn.evaluationLoading = false;
    trainingModeState.rnn.evaluationLoaded = false;
    trainingModeState.rnn.exportLoaded = false;
    trainingModeState.rnn.inferenceModelsLoaded = false;
    trainingModeState.rnn.inferenceResultLoaded = false;
    if (
      appState.currentProjectId
      && trainingModeState.activeMode === "rnn"
      && trainingModeState.activeRnnPanel === "evaluation"
    ) {
      window.setTimeout(() => loadRnnEvaluation({
        force: true,
        runId: appState.trainingStatus?.run_id || trainingModeState.rnn.evaluationRunId || ""
      }), 0);
    }
  });
  eventBus.on("training-status-changed", (change = {}) => {
    renderRnnLiveMonitor();
    updateRnnStartControls();
    const status = String(appState.trainingStatus?.status || "").toLowerCase();
    if (change.statusChanged && ["completed", "stopped", "failed"].includes(status)) {
      trainingModeState.rnn.evaluationRequestSeq += 1;
      trainingModeState.rnn.evaluationLoading = false;
      trainingModeState.rnn.evaluationLoaded = false;
      trainingModeState.rnn.evaluationRunMetrics = {};
      if (status === "completed" && appState.trainingStatus?.run_id) {
        trainingModeState.rnn.evaluationRunId = appState.trainingStatus.run_id;
      }
      if (trainingModeState.activeMode === "rnn" && trainingModeState.activeRnnPanel === "evaluation") {
        loadRnnEvaluation({ force: true, runId: appState.trainingStatus?.run_id || "" });
      }
    }
  });
  loadRnnModelGuides();
  renderTrainingModeSidebar();
  renderTrainingWorkspace();
}

function isHiddenModeNavButton(button) {
  return Boolean(button.closest(".training-mode-nav.hidden"));
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
  if (mode === "rnn") loadRnnConfig();
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
  const previousRnnPanel = trainingModeState.activeMode === "rnn" ? trainingModeState.activeRnnPanel : "";

  if (isRnnProject) {
    trainingModeState.activeMode = "rnn";
    trainingModeState.activeRnnPanel = targetPage === "training" && previousRnnPanel
      ? previousRnnPanel
      : "overview";
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

  setHTML("#rnn-training-flow-guide", renderTrainingFlowGuide({ mode: appState.currentProject ? "rnn" : null }));

  renderRnnReadiness();
  renderRnnLiveMonitor();
  if (!isCnn
    && appState.currentProjectId
    && !trainingModeState.rnn.config
    && !trainingModeState.rnn.configLoading
    && !trainingModeState.rnn.readiness
    && !trainingModeState.rnn.readinessLoading) {
    loadRnnConfig();
  }
  renderRnnSidebarReadiness(isCnn);
  toggleRnnEvaluationRightPanel(isRnnEvaluation);
  if (isRnnEvaluation) {
    loadRnnEvaluation();
  }
  if (!isCnn && appState.currentPage === "training" && trainingModeState.activeRnnPanel === "export") {
    renderRnnExportPanel();
    if (appState.currentProjectId && trainingModeState.rnn.exportProjectId !== appState.currentProjectId) {
      loadRnnExportModels();
    }
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
  [qs("#next-actions-list")?.closest(".workspace-context-card, .summary-section"), qs("#warning-list")?.closest(".workspace-context-card, .summary-section")]
    .filter(Boolean)
    .forEach((section) => {
      section.style.display = visible ? "none" : "";
    });
}

export function initRnnPreviewEvents() {
  preferGpuDevice("#rnn-device");
  preferGpuDevice("#rnn-inference-device");
  syncRnnAdvancedParameterControls();

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
  qs("#rnn-feature-checkbox-list")?.addEventListener("change", (event) => {
    if (!event.target.matches("input[type='checkbox'][data-rnn-feature-column]")) return;
    syncRnnFeatureInputFromCheckboxes(event.target);
    updateRnnFeatureWizardSummary();
    renderRnnFeatureCheckboxes();
  });
  qs("#rnn-feature-search")?.addEventListener("input", renderRnnFeatureCheckboxes);
  qsa("[data-rnn-feature-filter]").forEach((button) => button.addEventListener("click", () => {
    trainingModeState.rnn.featureFilter = button.dataset.rnnFeatureFilter || "all";
    renderRnnFeatureCheckboxes();
  }));
  qs("#rnn-feature-task-head")?.addEventListener("change", () => {
    const taskHead = qs("#rnn-feature-task-head")?.value || "classification";
    const trainingTaskHead = qs("#rnn-task-head");
    if (trainingTaskHead) trainingTaskHead.value = taskHead;
    renderRnnModelSelector();
    syncRnnModelSelection();
    renderRnnModelGuide();
    updateRnnFeatureWizardSummary();
  });
  ["#rnn-target-column", "#rnn-time-column", "#rnn-sequence-column"].forEach((selector) => {
    qs(selector)?.addEventListener("change", () => {
      reconcileRnnFeatureColumns();
      updateRnnFeatureWizardSummary();
    });
  });
  qs("#rnn-select-numeric-features")?.addEventListener("click", selectRnnNumericFeatures);
  qs("#rnn-exclude-target-features")?.addEventListener("click", () => {
    reconcileRnnFeatureColumns();
    updateRnnFeatureWizardSummary();
    renderRnnFeatureCheckboxes();
  });
  qs("#rnn-clear-features")?.addEventListener("click", () => {
    setRnnSelectedFeatureColumns([]);
    updateRnnFeatureWizardSummary();
    renderRnnFeatureCheckboxes();
  });
  qs("#rnn-save-feature-config")?.addEventListener("click", () => saveRnnFeatureConfig());
  qs("#rnn-model-family")?.addEventListener("change", () => {
    syncRnnModelSelection();
    syncRnnAdvancedParameterControls();
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
    const featureTaskHead = qs("#rnn-feature-task-head");
    if (featureTaskHead) featureTaskHead.value = qs("#rnn-task-head")?.value || "classification";
    renderRnnModelSelector();
    syncRnnModelSelection();
    renderRnnModelGuide();
    updateRnnFeatureWizardSummary();
    saveRnnFeatureConfig({ silent: true });
  });
  ["#rnn-start-disabled"].forEach((selector) => {
    qs(selector)?.addEventListener("click", startRnnTraining);
  });
  qs("#rnn-refresh-models")?.addEventListener("click", () => loadRnnInferenceModels({ force: true }));
  qs("#rnn-refresh-inference-result")?.addEventListener("click", () => loadLatestRnnInferenceResult({ force: true }));
  qs("#rnn-refresh-evaluation")?.addEventListener("click", () => loadRnnEvaluation({ force: true }));
  qs("#rnn-eval-run-select")?.addEventListener("change", (event) => selectRnnEvaluationRun(event.target.value));
  qs("#rnn-evaluation-panel")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-rnn-chart-download]");
    if (button) downloadRnnEvaluationChart(button.dataset.rnnChartDownload, button.dataset.metricIndex);
  });
  qs("#rnn-refresh-export-models")?.addEventListener("click", () => loadRnnExportModels({ force: true }));
  qs("#rnn-export-model")?.addEventListener("change", updateRnnExportControls);
  qsa("[data-rnn-export-format]").forEach((button) => {
    button.addEventListener("click", () => exportRnnArtifact(button.dataset.rnnExportFormat || "rnn_package"));
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
  ["#rnn-epochs", "#rnn-batch-size", "#rnn-device", "#rnn-hidden-size", "#rnn-layers", "#rnn-dropout", "#rnn-gradient-clip", "#rnn-early-stopping-patience", "#rnn-learning-rate", "#rnn-optimizer"].forEach((selector) => {
    qs(selector)?.addEventListener("input", renderRnnTrainingAdjustmentSummary);
  });
  qs("#rnn-lr-mode")?.addEventListener("change", syncRnnAdvancedParameterControls);
  qs("#rnn-early-stop-enabled")?.addEventListener("change", syncRnnAdvancedParameterControls);
}

async function loadRnnReadiness(options = {}) {
  if (!appState.currentProjectId || (trainingModeState.rnn.readinessLoading && !options.force)) {
    renderRnnReadiness();
    return;
  }

  const params = new URLSearchParams({
      sequence_length: qs("#rnn-sequence-length")?.value || "16",
      stride: qs("#rnn-stride")?.value || "8",
      horizon: qs("#rnn-horizon")?.value || "1"
  });
  const readinessKey = `${appState.currentProjectId}:${params.toString()}`;
  if (!options.force && trainingModeState.rnn.readiness && trainingModeState.rnn.readinessKey === readinessKey) {
    renderRnnReadiness();
    return;
  }
  trainingModeState.rnn.readinessLoading = true;
  renderRnnReadiness();
  try {
    trainingModeState.rnn.readiness = await apiFetch(
      `/api/projects/${appState.currentProjectId}/rnn/readiness?${params.toString()}`,
      { responseCacheTtlMs: options.force ? 0 : 30000 }
    );
    trainingModeState.rnn.readinessKey = readinessKey;
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
  const projectChanged = trainingModeState.rnn.configProjectId !== appState.currentProjectId;
  if (!projectChanged && trainingModeState.rnn.config && !options.force) {
    renderRnnConfig();
    return;
  }
  if (projectChanged) {
    trainingModeState.rnn.config = null;
    trainingModeState.rnn.readiness = null;
    trainingModeState.rnn.readinessKey = "";
    trainingModeState.rnn.schemaWizard = null;
    trainingModeState.rnn.qualityReport = null;
    trainingModeState.rnn.runRegistry = null;
  }
  trainingModeState.rnn.configLoading = true;
  renderRnnConfig();
  try {
    const payload = await apiFetch(`/api/projects/${appState.currentProjectId}/rnn/config`, {
      responseCacheTtlMs: options.force ? 0 : 30000
    });
    trainingModeState.rnn.config = payload.config || null;
    trainingModeState.rnn.configInspection = payload.inspection || null;
    trainingModeState.rnn.configRecommendation = payload.recommendation || payload.inspection?.suggested_config || null;
    trainingModeState.rnn.configValidation = payload.validation || null;
    trainingModeState.rnn.windowSummary = payload.window || payload.validation?.window || null;
    trainingModeState.rnn.configMismatches = payload.mismatches || [];
    trainingModeState.rnn.configProjectId = appState.currentProjectId;
    trainingModeState.rnn.configLoadedAt = Date.now();
    await loadRnnSchemaWizardAndQuality({ force: options.force });
    applyRnnConfigToForm();
    await loadRnnModelCatalog({ force: options.force });
    await loadRnnReadiness({ force: options.force });
  } catch (err) {
    eventBus.emit("toast", `RNN config load failed: ${err.message}`);
  } finally {
    trainingModeState.rnn.configLoading = false;
    renderRnnConfig();
  }
}

async function loadRnnSchemaWizardAndQuality(options = {}) {
  if (!appState.currentProjectId) return;
  const requestOptions = {
    suppressToast: true,
    responseCacheTtlMs: options.force ? 0 : 30000
  };
  const [wizardResult, qualityResult, registryResult] = await Promise.all([
    apiFetch(`/api/projects/${appState.currentProjectId}/rnn/schema-wizard`, requestOptions).catch(() => null),
    apiFetch(`/api/projects/${appState.currentProjectId}/dataset/quality-report`, requestOptions).catch(() => null),
    apiFetch(`/api/projects/${appState.currentProjectId}/train/runs/registry`, requestOptions).catch(() => null)
  ]);
  trainingModeState.rnn.schemaWizard = wizardResult?.wizard || null;
  trainingModeState.rnn.qualityReport = qualityResult || null;
  trainingModeState.rnn.runRegistry = registryResult || null;
}

function applyRnnConfigToForm() {
  const config = trainingModeState.rnn.config || {};
  const setValue = (selector, value) => {
    const el = qs(selector);
    if (el && value !== undefined && value !== null) el.value = value;
  };
  renderRnnFeatureControls();
  setValue("#rnn-feature-columns", (config.feature_columns || []).join(", "));
  setValue("#rnn-target-column", config.target_column || "");
  setValue("#rnn-sequence-column", config.sequence_column || "");
  setValue("#rnn-time-column", config.time_column || "");
  setValue("#rnn-sequence-length", config.sequence_length || 16);
  setValue("#rnn-stride", config.stride || 8);
  setValue("#rnn-horizon", config.horizon || 1);
  setValue("#rnn-task-head", config.task_head || "classification");
  setValue("#rnn-feature-task-head", config.task_head || "classification");
  renderRnnFeatureCheckboxes();
  updateRnnFeatureWizardSummary();
  syncRnnModelSelection();
  renderRnnModelGuide();
}

function parseRnnFeatureInput() {
  return parseRnnFeatureColumns(qs("#rnn-feature-columns")?.value || "");
}

function rnnInspectionHeaders() {
  return trainingModeState.rnn.configInspection?.headers || [];
}

function rnnPreviewRows() {
  return trainingModeState.rnn.configInspection?.preview_rows || [];
}

function selectedRnnFeatureColumns() {
  return parseRnnFeatureInput();
}

function isRnnColumnNumeric(name) {
  const rows = rnnPreviewRows();
  if (!rows.length) return !isRnnTimeColumn(name);
  const samples = rows.map((row) => row?.[name]).filter((value) => value !== undefined && value !== null && String(value).trim() !== "");
  if (!samples.length) return !isRnnTimeColumn(name);
  return samples.every((value) => Number.isFinite(Number(String(value).trim())));
}

function isRnnTimeColumn(name = "") {
  return /(^|[_\s-])(date|time|timestamp|timestep)([_\s-]|$)/i.test(name);
}

function isRnnSequenceColumn(name = "") {
  return /(sequence|seq|series|machine|batch|asset|unit).*id|id.*(sequence|seq|series|machine|batch|asset|unit)/i.test(name);
}

function isRnnLabelColumn(name = "") {
  return /(^|[_\s-])(label|class|category|target|y|fault|state|status)([_\s-]|$)/i.test(name);
}

function detectRnnRecommendedConfig() {
  const backendRecommendation = trainingModeState.rnn.configRecommendation || trainingModeState.rnn.configInspection?.suggested_config;
  if (backendRecommendation) {
    return {
      taskHead: backendRecommendation.task_head || "regression",
      targetColumn: backendRecommendation.target_column || "",
      timeColumn: backendRecommendation.time_column || "",
      sequenceColumn: backendRecommendation.sequence_column || "",
      featureColumns: Array.isArray(backendRecommendation.feature_columns) ? backendRecommendation.feature_columns : [],
      confidence: backendRecommendation.recommendation_confidence || "unknown",
      reason: backendRecommendation.recommendation_reason || "",
      source: "backend"
    };
  }
  const headers = rnnInspectionHeaders();
  const numericColumns = headers.filter((name) => isRnnColumnNumeric(name));
  const timeColumn = headers.find(isRnnTimeColumn) || "";
  const sequenceColumn = headers.find(isRnnSequenceColumn) || "";
  const labelColumn = headers.find((name) => isRnnLabelColumn(name) && !isRnnColumnNumeric(name)) || "";
  const targetColumn = labelColumn || headers.find((name) => isRnnLabelColumn(name) && isRnnColumnNumeric(name)) || "";
  const taskHead = labelColumn ? "classification" : "regression";
  const excluded = new Set([targetColumn, timeColumn, sequenceColumn].filter(Boolean));
  const featureColumns = numericColumns.filter((name) => !excluded.has(name));
  return {
    taskHead,
    targetColumn,
    timeColumn,
    sequenceColumn,
    featureColumns,
    labelColumn,
    numericColumns,
    confidence: targetColumn ? "fallback" : "needs_user",
    reason: targetColumn ? "Target inferred from common label/target/y column names." : "No explicit target column detected. Select the prediction target manually.",
    source: "fallback"
  };
}

function renderRnnFeatureControls() {
  const headers = rnnInspectionHeaders();
  renderRnnColumnSelect("#rnn-target-column", headers, t("rnn.schemaWizard.targetPlaceholder"));
  renderRnnColumnSelect("#rnn-time-column", headers, t("rnn.schemaWizard.noTimeColumn"));
  renderRnnColumnSelect("#rnn-sequence-column", headers, t("rnn.schemaWizard.noSequenceColumn"));
  renderRnnFeatureCheckboxes();
}

function renderRnnColumnSelect(selector, headers = [], emptyLabel = "None") {
  const select = qs(selector);
  if (!select) return;
  const current = select.value;
  const options = [`<option value="">${escapeHtml(emptyLabel)}</option>`]
    .concat(headers.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`));
  select.innerHTML = options.join("");
  if (current && headers.includes(current)) select.value = current;
}

function renderRnnFeatureCheckboxes() {
  const container = qs("#rnn-feature-checkbox-list");
  if (!container) return;
  const headers = rnnInspectionHeaders();
  const selected = new Set(selectedRnnFeatureColumns());
  const target = qs("#rnn-target-column")?.value || "";
  const time = qs("#rnn-time-column")?.value || "";
  const sequence = qs("#rnn-sequence-column")?.value || "";
  const query = (qs("#rnn-feature-search")?.value || "").trim().toLowerCase();
  const activeFilter = trainingModeState.rnn.featureFilter || "all";
  qsa("[data-rnn-feature-filter]").forEach((button) => {
    const active = button.dataset.rnnFeatureFilter === activeFilter;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  if (!headers.length) {
    container.innerHTML = `<div class="rnn-empty-feature-list">${escapeHtml(t("rnn.schemaWizard.importForFeatures"))}</div>`;
    setText("#rnn-feature-visible-count", "0 / 0");
    return;
  }
  const featureModels = headers.map((name) => {
    const reserved = name === target || name === time || name === sequence;
    const numeric = isRnnColumnNumeric(name);
    const checked = selected.has(name) && !reserved;
    return { name, reserved, numeric, checked };
  });
  const visibleModels = featureModels.filter((item) => {
    if (query && !item.name.toLowerCase().includes(query)) return false;
    if (activeFilter === "selected") return item.checked;
    if (activeFilter === "warning") return item.reserved;
    return true;
  });
  setText("#rnn-feature-visible-count", t("rnn.featureWorkbench.visibleCount", {
    visible: visibleModels.length,
    total: featureModels.length,
  }));
  if (!visibleModels.length) {
    container.innerHTML = `<div class="rnn-empty-feature-list">${escapeHtml(t("rnn.featureWorkbench.noMatches"))}</div>`;
    return;
  }
  container.innerHTML = visibleModels.map(({ name, reserved, numeric, checked }) => {
    return `<label class="rnn-feature-check ${reserved ? "reserved" : ""}">
      <input type="checkbox" data-rnn-feature-column="${escapeHtml(name)}" value="${escapeHtml(name)}" ${checked ? "checked" : ""} ${reserved ? "disabled" : ""}>
      <span>
        <strong>${escapeHtml(name)}</strong>
        <em>${escapeHtml(reserved ? t("rnn.schemaWizard.reserved") : numeric ? t("rnn.schemaWizard.numeric") : t("rnn.schemaWizard.text"))}</em>
      </span>
    </label>`;
  }).join("");
}

function syncRnnFeatureInputFromCheckboxes(changedInput = null) {
  if (changedInput?.matches?.("[data-rnn-feature-column]")) {
    const features = new Set(selectedRnnFeatureColumns());
    if (changedInput.checked) features.add(changedInput.value);
    else features.delete(changedInput.value);
    setRnnSelectedFeatureColumns([...features]);
    return;
  }
  const features = qsa("[data-rnn-feature-column]:checked").map((input) => input.value);
  setRnnSelectedFeatureColumns(features);
}

function setRnnSelectedFeatureColumns(features = []) {
  const input = qs("#rnn-feature-columns");
  const normalized = [...new Set((features || []).filter(Boolean))];
  if (input) input.value = normalized.join(", ");
  qsa("[data-rnn-feature-column]").forEach((checkbox) => {
    checkbox.checked = normalized.includes(checkbox.value) && !checkbox.disabled;
  });
}

function reconcileRnnFeatureColumns() {
  const reserved = new Set([
    qs("#rnn-target-column")?.value || "",
    qs("#rnn-time-column")?.value || "",
    qs("#rnn-sequence-column")?.value || ""
  ].filter(Boolean));
  const features = selectedRnnFeatureColumns().filter((name) => !reserved.has(name));
  setRnnSelectedFeatureColumns(features);
  renderRnnFeatureCheckboxes();
}

function selectRnnNumericFeatures() {
  const reserved = new Set([
    qs("#rnn-target-column")?.value || "",
    qs("#rnn-time-column")?.value || "",
    qs("#rnn-sequence-column")?.value || ""
  ].filter(Boolean));
  const features = rnnInspectionHeaders().filter((name) => isRnnColumnNumeric(name) && !reserved.has(name));
  setRnnSelectedFeatureColumns(features);
  renderRnnFeatureCheckboxes();
  updateRnnFeatureWizardSummary();
}

function updateRnnFeatureWizardSummary() {
  const inspection = trainingModeState.rnn.configInspection || {};
  const recommendation = detectRnnRecommendedConfig();
  const taskHead = qs("#rnn-feature-task-head")?.value || qs("#rnn-task-head")?.value || recommendation.taskHead;
  const target = qs("#rnn-target-column")?.value || "";
  const featureCount = selectedRnnFeatureColumns().length;
  setText("#rnn-feature-summary-rows", inspection.row_count ? String(inspection.row_count) : "--");
  setText("#rnn-feature-summary-task", taskHead === "regression" ? t("rnn.task.regression") : t("rnn.task.classification"));
  setText("#rnn-feature-summary-x", t("rnn.featureSummary.featureCount", { count: featureCount }));
  setText("#rnn-feature-summary-y", target || t("common.notSet"));
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
    task_head: qs("#rnn-feature-task-head")?.value || qs("#rnn-task-head")?.value || "classification"
  };
  try {
    const result = await apiFetch(`/api/projects/${appState.currentProjectId}/rnn/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    trainingModeState.rnn.config = result.config || payload;
    trainingModeState.rnn.configInspection = result.inspection || trainingModeState.rnn.configInspection;
    trainingModeState.rnn.configRecommendation = result.recommendation || result.inspection?.suggested_config || trainingModeState.rnn.configRecommendation;
    trainingModeState.rnn.configValidation = result.validation || null;
    trainingModeState.rnn.windowSummary = result.window || result.validation?.window || null;
    trainingModeState.rnn.configMismatches = result.mismatches || [];
    await loadRnnSchemaWizardAndQuality();
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
  if (label) label.textContent = file ? file.name : t("rnn.dataset.dropTitle");
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
  const progress = beginTask({
    jobId: `rnn-dataset-import-${Date.now()}`,
    kind: "import",
    title: t("rnn.dataset.progress.title"),
    stage: t("rnn.dataset.progress.preparing"),
    message: t("rnn.dataset.progress.preparing"),
    method: "POST",
    delayMs: 0,
    button: qs("#rnn-import-dataset"),
    inlineHost: qs("#rnn-sequence-dataset-panel .rnn-sequence-dataset-card"),
  });
  progress.show();
  progress.update({ percent: 2, indeterminate: false, message: t("rnn.dataset.progress.preparing") });
  try {
    const form = new FormData();
    form.append("file", file);
    const result = await apiUpload(`/api/projects/${appState.currentProjectId}/rnn/dataset/import`, {
      method: "POST",
      body: form,
      suppressProgress: true,
      onUploadProgress: ({ phase, percent, indeterminate }) => {
        if (phase === "processing") {
          progress.update({ percent: 78, indeterminate: true, message: t("rnn.dataset.progress.processing") });
          return;
        }
        const uploadPercent = Math.max(3, Math.min(75, 3 + ((Number(percent) || 0) * 0.72)));
        progress.update({
          percent: uploadPercent,
          indeterminate: Boolean(indeterminate),
          message: indeterminate
            ? t("rnn.dataset.progress.uploadingUnknown")
            : t("rnn.dataset.progress.uploading", { percent: Math.round(Number(percent) || 0) }),
        });
      },
    });
    progress.update({ percent: 82, indeterminate: false, message: t("rnn.dataset.progress.readingSchema") });
    trainingModeState.rnn.config = result.config || null;
    trainingModeState.rnn.configInspection = result.dataset?.inspection || result.inspection || null;
    trainingModeState.rnn.configRecommendation = result.recommendation || result.dataset?.suggested_config || result.dataset?.inspection?.suggested_config || null;
    trainingModeState.rnn.configValidation = result.validation || null;
    trainingModeState.rnn.windowSummary = result.window || result.validation?.window || null;
    trainingModeState.rnn.configMismatches = result.mismatches || [];
    await loadRnnSchemaWizardAndQuality();
    progress.update({ percent: 91, indeterminate: false, message: t("rnn.dataset.progress.buildingPreview") });
    applyRnnConfigToForm();
    progress.update({ percent: 96, indeterminate: false, message: t("rnn.dataset.progress.checkingReadiness") });
    await loadRnnReadiness({ force: true });
    progress.complete({ message: t("rnn.dataset.progress.completed", { name: file.name }) });
    eventBus.emit("toast", t("rnn.dataset.imported"));
  } catch (err) {
    progress.fail({ message: t("rnn.dataset.progress.failed", { message: err.message }) });
    eventBus.emit("toast", t("rnn.dataset.importFailed", { message: err.message }));
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
  const importButton = qs("#rnn-import-dataset");
  const refreshButton = qs("#rnn-refresh-config");
  if (importButton) importButton.disabled = trainingModeState.rnn.datasetImporting;
  if (refreshButton) refreshButton.disabled = trainingModeState.rnn.datasetImporting;
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
  renderRnnFeatureControls();
  updateRnnFeatureWizardSummary();
  renderRnnDatasetQualityReport();
  renderRnnWindowSummary(validation);
  renderRnnConfigMismatch();
  renderRnnModelGuide();
}

function renderRnnDatasetQualityReport() {
  const host = qs("#rnn-dataset-quality-report");
  if (!host) return;
  const report = trainingModeState.rnn.qualityReport;
  if (!report) {
    host.innerHTML = "";
    return;
  }
  const checks = report.checks || [];
  const warnings = checks.filter((item) => item.status !== "pass");
  const summary = report.summary || {};
  const missing = report.missing_values?.high_missing_columns || [];
  const healthScore = Number(report.health_score || 0);
  const warningMessages = warnings.slice(0, 3).map((item) => {
    const key = `rnn.quality.warning.${item.name || "unknown"}`;
    const translated = t(key);
    return translated && translated !== key ? translated : item.message;
  });
  host.innerHTML = `
    <div class="rnn-quality-head">
      <strong>${escapeHtml(t("rnn.quality.title"))}</strong>
      <span class="summary-badge ${healthScore >= 80 ? "badge-success" : "badge-warning"}">${escapeHtml(String(healthScore))}%</span>
    </div>
    <div class="rnn-quality-summary-list">
      <div><span>${escapeHtml(t("rnn.quality.rows"))}</span><strong>${escapeHtml(String(summary.row_count ?? summary.image_count ?? "--"))}</strong></div>
      <div><span>${escapeHtml(t("rnn.quality.warnings"))}</span><strong>${warnings.length}</strong></div>
    </div>
    ${missing.length ? `<div class="rnn-quality-warning">${escapeHtml(t("rnn.quality.highMissing"))}: ${missing.slice(0, 4).map((item) => escapeHtml(item.column)).join(", ")}</div>` : ""}
    ${warningMessages.length ? `<div class="rnn-quality-warning">${warningMessages.map((item) => escapeHtml(item)).join(" · ")}</div>` : ""}
  `;
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

  setText("#rnn-context-window-count", String(sequenceCount || "--"));
  setText("#rnn-context-feature-count", String(featureDim || "--"));
  setText("#rnn-context-sequence-length", String(trainingModeState.rnn.config?.sequence_length || qs("#rnn-sequence-length")?.value || "--"));
  renderRnnTrainingAdjustmentSummary();

  setText("#rnn-manifest-status", manifest.exists ? t("rnn.sequenceCountValue", { count: manifest.sequence_count || 0 }) : t("rnn.readiness.manifestNotConnected"));
  setText("#rnn-source-status", source === "manifest" ? "sequence_manifest.json" : source === "csv" ? `${csvFiles} CSV feature file(s)` : t("rnn.readiness.noSequenceSource"));
  setText("#rnn-split-status", splitText);
  setText("#rnn-feature-columns-status", csv.feature_dim
    ? t("rnn.readiness.csvFeatureColumns", { count: csv.feature_dim })
    : requirements.feature_dim
      ? t("rnn.readiness.manifestFeatureDim", { count: featureDim })
      : t("rnn.readiness.notParsed"));
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

function renderRnnLiveMonitor() {
  const host = qs("#rnn-live-monitor");
  if (!host) return;
  const view = buildRnnLiveMonitorViewModel(appState.trainingStatus || {});
  const isRnnProject = String(appState.currentProject?.task_type || "").toLowerCase().includes("sequence");
  host.classList.toggle("is-active", view.visible && ["training", "stopping"].includes(view.status));
  setText("#rnn-monitor-status", trainingStatusLabelForRnn(view.status));
  setText("#rnn-monitor-progress-text", `Epoch ${Math.min(view.epoch, view.totalEpochs || view.epoch)} / ${view.totalEpochs || "--"}`);
  setText("#rnn-monitor-progress-percent", `${Math.round(view.progress)}%`);
  const progressBar = qs("#rnn-monitor-progress-bar");
  if (progressBar) progressBar.style.width = `${view.progress}%`;

  const cards = qs("#rnn-monitor-metrics");
  if (cards) {
    cards.innerHTML = view.cards.map((card) => `
      <div class="metric-card">
        <span>${escapeHtml(card.label)}</span>
        <strong>${card.value === null ? "--" : escapeHtml(Number(card.value).toFixed(4))}</strong>
      </div>
    `).join("");
  }
  renderRnnMonitorChart("rnn-monitor-quality-chart", "rnn-monitor-quality-empty", view.qualityChart, "score");
  renderRnnMonitorChart("rnn-monitor-loss-chart", "rnn-monitor-loss-empty", view.lossChart, "loss");
  if (!view.visible && !isRnnProject) {
    setText("#rnn-monitor-status", t("training.monitor.statusIdle"));
  }
}

function trainingStatusLabelForRnn(status = "idle") {
  const keys = {
    training: "training.progress.inProgress",
    stopping: "training.progress.stopping",
    completed: "common.completed",
    failed: "common.failed",
    stopped: "common.stopped",
    idle: "training.monitor.statusIdle"
  };
  return t(keys[status] || keys.idle);
}

function renderRnnMonitorChart(canvasId, emptyId, chartModel, variant) {
  const canvas = qs(`#${canvasId}`);
  const empty = qs(`#${emptyId}`);
  if (!canvas) return;
  const hasSeries = chartModel?.series?.some((item) => item.values?.some((value) => value !== null));
  canvas.classList.toggle("hidden", !hasSeries);
  empty?.classList.toggle("hidden", hasSeries);
  const signature = JSON.stringify({ labels: chartModel?.labels || [], series: chartModel?.series || [] });
  if (hasSeries && rnnMonitorChartSignatures.get(canvasId) === signature) return;
  rnnMonitorChartSignatures.set(canvasId, signature);
  const previous = canvasId === "rnn-monitor-quality-chart" ? rnnMonitorQualityChart : rnnMonitorLossChart;
  previous?.destroy();
  if (typeof Chart !== "undefined" && typeof Chart.getChart === "function") {
    Chart.getChart(canvas)?.destroy();
  }
  if (!hasSeries || typeof Chart === "undefined") {
    if (canvasId === "rnn-monitor-quality-chart") rnnMonitorQualityChart = null;
    else rnnMonitorLossChart = null;
    return;
  }
  const palette = variant === "loss" ? ["#ef4444", "#f59e0b"] : ["#3b82f6", "#22c55e", "#a855f7", "#f59e0b"];
  const chart = new Chart(canvas, {
    type: "line",
    data: {
      labels: chartModel.labels,
      datasets: chartModel.series.map((series, index) => ({
        label: series.label,
        data: series.values,
        borderColor: palette[index % palette.length],
        backgroundColor: palette[index % palette.length],
        tension: 0.25,
        pointRadius: 2,
        borderWidth: 2.2,
        spanGaps: false
      }))
    },
    options: buildRnnChartOptions(variant === "loss" ? t("rnn.evaluation.lossCurve") : t("rnn.monitor.qualityChart"))
  });
  if (canvasId === "rnn-monitor-quality-chart") rnnMonitorQualityChart = chart;
  else rnnMonitorLossChart = chart;
}

async function loadRnnEvaluation(options = {}) {
  if (!appState.currentProjectId) {
    trainingModeState.rnn.evaluationProjectId = "";
    trainingModeState.rnn.evaluationRuns = [];
    trainingModeState.rnn.evaluationMetrics = null;
    trainingModeState.rnn.evaluationArtifacts = [];
    trainingModeState.rnn.evaluationRunId = "";
    trainingModeState.rnn.evaluationRunMetrics = {};
    trainingModeState.rnn.evaluationLoaded = false;
    renderRnnEvaluation();
    return;
  }
  const projectId = appState.currentProjectId;
  if (trainingModeState.rnn.evaluationLoading && !options.force) {
    renderRnnEvaluation();
    return;
  }
  const projectChanged = trainingModeState.rnn.evaluationProjectId !== projectId;
  if (projectChanged) {
    trainingModeState.rnn.evaluationRequestSeq += 1;
    trainingModeState.rnn.evaluationProjectId = projectId;
    trainingModeState.rnn.evaluationRuns = [];
    trainingModeState.rnn.evaluationMetrics = null;
    trainingModeState.rnn.evaluationArtifacts = [];
    trainingModeState.rnn.evaluationRunId = "";
    trainingModeState.rnn.evaluationRunMetrics = {};
    trainingModeState.rnn.evaluationLoaded = false;
  }
  if (!projectChanged && !options.force && trainingModeState.rnn.evaluationLoaded) {
    renderRnnEvaluation();
    return;
  }

  const requestSeq = trainingModeState.rnn.evaluationRequestSeq + 1;
  trainingModeState.rnn.evaluationRequestSeq = requestSeq;
  trainingModeState.rnn.evaluationActiveRequestSeq = requestSeq;
  trainingModeState.rnn.evaluationLoading = true;
  renderRnnEvaluation();
  try {
    const runsPayload = await apiFetch(`/api/projects/${projectId}/train/runs`, { dedupe: false, suppressProgress: true });
    const runs = sortRnnEvaluationRuns((Array.isArray(runsPayload) ? runsPayload : []).filter(isSequenceEvaluationRun));
    const preferredRunId = options.runId || (!projectChanged ? trainingModeState.rnn.evaluationRunId : "");
    const activeRun = runs.find((run) => run.run_id === preferredRunId) || runs[0] || null;
    if (!activeRun?.run_id) {
      if (requestSeq !== trainingModeState.rnn.evaluationRequestSeq || projectId !== appState.currentProjectId) return;
      trainingModeState.rnn.evaluationProjectId = projectId;
      trainingModeState.rnn.evaluationRuns = runs;
      trainingModeState.rnn.evaluationMetrics = null;
      trainingModeState.rnn.evaluationArtifacts = [];
      trainingModeState.rnn.evaluationRunId = "";
      trainingModeState.rnn.evaluationRunMetrics = {};
      trainingModeState.rnn.evaluationLoaded = true;
      return;
    }

    const runMetricEntries = await Promise.all(runs.map(async (run) => {
      try {
        const payload = await apiFetch(`/api/projects/${projectId}/train/runs/${encodeURIComponent(run.run_id)}/metrics`, {
          suppressToast: true,
          suppressProgress: true,
          dedupe: false
        });
        return [run.run_id, payload || null];
      } catch (err) {
        return [run.run_id, null];
      }
    }));
    const metricsByRun = Object.fromEntries(runMetricEntries.filter(([runId, payload]) => runId && payload));
    let metrics = metricsByRun[activeRun.run_id] || null;
    const [artifacts] = await Promise.all([
      apiFetch(`/api/projects/${projectId}/train/runs/${encodeURIComponent(activeRun.run_id)}/artifacts`, {
        suppressProgress: true,
        dedupe: false
      })
    ]);
    if (!hasUsableRnnEvaluationMetrics(metrics)) {
      metrics = await apiFetch(
        `/api/projects/${projectId}/train/runs/${encodeURIComponent(activeRun.run_id)}/metrics`,
        { suppressToast: true, suppressProgress: true, dedupe: false }
      );
      if (metrics) metricsByRun[activeRun.run_id] = metrics;
    }
    if (requestSeq !== trainingModeState.rnn.evaluationRequestSeq || projectId !== appState.currentProjectId) return;
    trainingModeState.rnn.evaluationProjectId = projectId;
    trainingModeState.rnn.evaluationRuns = runs;
    trainingModeState.rnn.evaluationMetrics = metrics || null;
    trainingModeState.rnn.evaluationArtifacts = Array.isArray(artifacts) ? artifacts : [];
    trainingModeState.rnn.evaluationRunId = activeRun.run_id;
    trainingModeState.rnn.evaluationRunMetrics = metricsByRun;
    trainingModeState.rnn.evaluationLoaded = true;
  } catch (err) {
    if (requestSeq !== trainingModeState.rnn.evaluationRequestSeq) return;
    eventBus.emit("toast", `RNN evaluation load failed: ${err.message}`);
    trainingModeState.rnn.evaluationMetrics = null;
    trainingModeState.rnn.evaluationArtifacts = [];
    trainingModeState.rnn.evaluationRunMetrics = {};
    trainingModeState.rnn.evaluationLoaded = false;
  } finally {
    if (requestSeq !== trainingModeState.rnn.evaluationRequestSeq) {
      if (trainingModeState.rnn.evaluationActiveRequestSeq === requestSeq) {
        trainingModeState.rnn.evaluationActiveRequestSeq = 0;
        trainingModeState.rnn.evaluationLoading = false;
        if (
          appState.currentProjectId === projectId
          && trainingModeState.activeMode === "rnn"
          && trainingModeState.activeRnnPanel === "evaluation"
        ) {
          window.setTimeout(() => loadRnnEvaluation({
            force: true,
            runId: options.runId || trainingModeState.rnn.evaluationRunId || ""
          }), 0);
        }
      }
      return;
    }
    trainingModeState.rnn.evaluationActiveRequestSeq = 0;
    trainingModeState.rnn.evaluationLoading = false;
    renderRnnEvaluation();
  }
}

async function selectRnnEvaluationRun(runId) {
  const projectId = appState.currentProjectId;
  if (!projectId) return;
  const runs = trainingModeState.rnn.evaluationRuns || [];
  const activeRun = runs.find((run) => run.run_id === runId) || runs[0] || null;
  if (!activeRun?.run_id) {
    trainingModeState.rnn.evaluationRunId = "";
    trainingModeState.rnn.evaluationMetrics = null;
    trainingModeState.rnn.evaluationArtifacts = [];
    renderRnnEvaluation();
    return;
  }

  const requestSeq = trainingModeState.rnn.evaluationRequestSeq + 1;
  trainingModeState.rnn.evaluationRequestSeq = requestSeq;
  trainingModeState.rnn.evaluationActiveRequestSeq = requestSeq;
  trainingModeState.rnn.evaluationLoading = true;
  trainingModeState.rnn.evaluationRunId = activeRun.run_id;
  trainingModeState.rnn.evaluationMetrics = trainingModeState.rnn.evaluationRunMetrics?.[activeRun.run_id] || null;
  trainingModeState.rnn.evaluationArtifacts = [];
  renderRnnEvaluation();
  try {
    const [metrics, artifacts] = await Promise.all([
      apiFetch(`/api/projects/${projectId}/train/runs/${encodeURIComponent(activeRun.run_id)}/metrics`, {
        suppressToast: true,
        suppressProgress: true,
        dedupe: false
      }),
      apiFetch(`/api/projects/${projectId}/train/runs/${encodeURIComponent(activeRun.run_id)}/artifacts`, {
        suppressToast: true,
        suppressProgress: true,
        dedupe: false
      })
    ]);
    if (requestSeq === trainingModeState.rnn.evaluationRequestSeq && trainingModeState.rnn.evaluationRunId === activeRun.run_id) {
      trainingModeState.rnn.evaluationMetrics = metrics || null;
      if (metrics) trainingModeState.rnn.evaluationRunMetrics[activeRun.run_id] = metrics;
      trainingModeState.rnn.evaluationArtifacts = Array.isArray(artifacts) ? artifacts : [];
    }
  } catch (err) {
    if (requestSeq === trainingModeState.rnn.evaluationRequestSeq && trainingModeState.rnn.evaluationRunId === activeRun.run_id) {
      trainingModeState.rnn.evaluationArtifacts = [];
    }
  } finally {
    if (requestSeq !== trainingModeState.rnn.evaluationRequestSeq) return;
    trainingModeState.rnn.evaluationActiveRequestSeq = 0;
    trainingModeState.rnn.evaluationLoading = false;
    renderRnnEvaluation();
  }
}

function hasUsableRnnEvaluationMetrics(metrics) {
  if (!metrics || typeof metrics !== "object") return false;
  if (Array.isArray(metrics.history) && metrics.history.length) return true;
  if (metrics.best_metrics && Object.keys(metrics.best_metrics).length) return true;
  if (Array.isArray(metrics.residuals) && metrics.residuals.length) return true;
  if (Array.isArray(metrics.prediction_actual_samples) && metrics.prediction_actual_samples.length) return true;
  if (Array.isArray(metrics.confusion_matrix) && metrics.confusion_matrix.length) return true;
  return false;
}

function sortRnnEvaluationRuns(runs = []) {
  return [...runs].sort((a, b) => {
    const timeA = Date.parse(a?.completed_at || a?.updated_at || a?.created_at || a?.started_at || "");
    const timeB = Date.parse(b?.completed_at || b?.updated_at || b?.created_at || b?.started_at || "");
    return (Number.isFinite(timeB) ? timeB : 0) - (Number.isFinite(timeA) ? timeA : 0);
  });
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
    taskType,
    metricSchema,
    metricSource,
    isRegression,
    primary,
    secondary
  } = resolveRnnEvaluationViewModel({
    runs,
    metrics,
    selectedRunId: trainingModeState.rnn.evaluationRunId
  });

  const overview = resolveRnnEvaluationOverviewRender({
    hasMetrics: Boolean(metrics),
    loading: trainingModeState.rnn.evaluationLoading,
    activeRun,
    backend: sequenceBackendLabel(summary),
    primary,
    secondary,
    metricSource
  });

  if (badge) {
    badge.className = overview.badge.className;
    badge.textContent = overview.badge.text;
  }

  setText("#rnn-eval-primary-label", overview.primaryLabel);
  setText("#rnn-eval-primary-value", overview.primaryValue);
  setText("#rnn-eval-secondary-label", overview.secondaryLabel);
  setText("#rnn-eval-secondary-value", overview.secondaryValue);
  setText("#rnn-eval-primary-history-label", overview.primaryLabel);
  setText("#rnn-eval-secondary-history-label", overview.secondaryLabel);
  setText("#rnn-eval-train-loss", overview.trainLoss);
  setText("#rnn-eval-val-loss", overview.valLoss);
  renderRnnEvaluationRunSelector({
    runs,
    activeRun,
    metricsByRun: trainingModeState.rnn.evaluationRunMetrics || {},
    loading: trainingModeState.rnn.evaluationLoading
  });

  if (message) {
    message.classList.toggle("hidden", overview.message.hidden);
    message.textContent = overview.message.text;
  }

  renderRnnEvaluationEpochRows(history);
  const dashboard = buildRnnTaskAwareDashboard({
    metrics,
    summary,
    history,
    runs,
    metricsByRun: trainingModeState.rnn.evaluationRunMetrics || {},
    comparisonMetric: trainingModeState.rnn.comparisonMetric || "macro_f1"
  });
  currentRnnEvaluationDashboard = activeRun ? dashboard : null;
  renderRnnTaskAwareDashboard(dashboard, { history, isRegression, metricContext: metrics || summary });
  renderRnnSmartAssessment(activeRun ? buildRnnSmartAssessment({
    metrics: metrics || {},
    summary,
    config: trainingModeState.rnn.config || {}
  }) : {});
  renderRnnEvaluationArtifacts(artifacts, activeRun?.run_id || "");
  renderRnnEvaluationRunHistory(runs);
  renderRnnEvaluationSidebar({
    activeRun,
    metrics,
    artifacts,
    history,
    taskType,
    metricSchema,
    metricSource,
    isRegression,
    primary,
    secondary
  });
}

function renderRnnEvaluationRunSelector({ runs = [], activeRun = null, metricsByRun = {}, loading = false } = {}) {
  const select = qs("#rnn-eval-run-select");
  const label = qs("#rnn-eval-active-run-label");
  if (!select && !label) return;
  if (select) {
    select.innerHTML = renderRnnEvaluationRunSelectorOptions({ runs, selectedRunId: activeRun?.run_id || "", metricsByRun });
    select.value = activeRun?.run_id || "";
    select.disabled = loading || !runs.length;
  }
  if (label) {
    if (!activeRun?.run_id) {
      label.textContent = loading ? t("rnn.evaluation.loadingRunHistory") : t("rnn.evaluation.noActiveRun");
      return;
    }
    const metrics = metricsByRun[activeRun.run_id] || {};
    const epochCount = Array.isArray(metrics.history) && metrics.history.length
      ? metrics.history.length
      : Number(activeRun.best_epoch || activeRun.epochs || 0);
    const parts = [
      activeRun.run_id,
      sequenceBackendLabel(activeRun),
      epochCount ? `${epochCount} epoch${epochCount === 1 ? "" : "s"}` : "",
      activeRun.completed_at || activeRun.updated_at || activeRun.started_at || ""
    ].filter(Boolean);
    label.textContent = `Viewing ${parts.join(" / ")}`;
  }
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

function renderRnnTaskAwareDashboard(dashboard, fallback = {}) {
  setText("#rnn-eval-chart-count", t("rnn.evaluation.metricCount", { count: dashboard.chartCount || 0 }));
  setText("#rnn-eval-score-chart-title", dashboard.scoreChart?.title || t("rnn.evaluation.scoreCurve"));
  setText("#rnn-eval-score-chart-note", dashboard.scoreChart?.note || t("rnn.evaluation.scoreCurveNote"));
  setText("#rnn-eval-loss-chart-title", dashboard.lossChart?.title || t("rnn.evaluation.lossCurve"));
  setText("#rnn-eval-loss-chart-note", dashboard.lossChart?.note || t("rnn.evaluation.lossCurveNote"));
  setText("#rnn-eval-diagnostic-title", dashboard.diagnostic?.title || t("rnn.evaluation.taskDiagnostic"));
  setText("#rnn-eval-diagnostic-badge", dashboard.diagnostic?.badge || "schema");

  const baselineNote = qs("#rnn-eval-baseline-note");
  const trendRows = buildRnnMetricTrendRows(fallback);
  baselineNote?.classList.toggle("hidden", !trendRows.isSinglePointBaseline);

  if (typeof Chart === "undefined") {
    renderRnnMetricTrendRows(fallback.history, fallback.isRegression, fallback.metricContext);
  } else {
    renderRnnLineChart("rnn-eval-score-chart", "rnn-eval-score-empty", dashboard.scoreChart, "score");
    renderRnnLineChart("rnn-eval-loss-chart", "rnn-eval-loss-empty", dashboard.lossChart, "loss");
  }

  renderRnnBaselineComparison(dashboard.metricSchema);
  const diagnosticHost = qs("#rnn-eval-task-diagnostic");
  if (diagnosticHost) diagnosticHost.innerHTML = renderRnnTaskDiagnostic(dashboard.diagnostic);
}

function renderRnnSmartAssessment(assessment = {}) {
  const score = qs("#rnn-intelligence-score");
  const verdict = qs("#rnn-intelligence-verdict");
  const context = qs("#rnn-intelligence-context");
  const recommendations = qs("#rnn-intelligence-recommendations");
  if (score) score.textContent = assessment.score ?? "--";
  if (verdict) {
    verdict.textContent = assessment.verdict ? t(`rnn.intelligence.verdict.${assessment.verdict}`) : "--";
    verdict.className = `summary-badge rnn-verdict-${assessment.verdict || "neutral"}`;
  }
  if (context) {
    context.innerHTML = (assessment.context || []).map(([label, value]) => `
      <span><small>${escapeHtml(label)}</small><strong>${escapeHtml(value)}</strong></span>
    `).join("");
  }
  if (recommendations) {
    recommendations.innerHTML = (assessment.signals || []).map((signal) => `
      <div class="rnn-intelligence-signal is-${escapeHtml(signal.tone || "info")}">
        <i class="fa-solid ${signal.tone === "success" ? "fa-circle-check" : signal.tone === "danger" ? "fa-circle-xmark" : "fa-lightbulb"}"></i>
        <div><strong>${escapeHtml(t(`rnn.intelligence.signal.${signal.code}.title`, signal.values || {}))}</strong><span>${escapeHtml(t(`rnn.intelligence.signal.${signal.code}.help`, signal.values || {}))}</span></div>
      </div>
    `).join("");
  }
}

function downloadRnnEvaluationChart(kind, metricIndex) {
  if (!currentRnnEvaluationDashboard) {
    eventBus.emit("toast", t("rnn.evaluation.downloadUnavailable"));
    return;
  }
  let svg = "";
  let filename = "rnn-chart.svg";
  if (kind === "score" || kind === "loss") {
    const model = kind === "score" ? currentRnnEvaluationDashboard.scoreChart : currentRnnEvaluationDashboard.lossChart;
    svg = buildRnnLineChartSvg(model || {});
    filename = `rnn-${kind}-curve.svg`;
  } else if (kind === "comparison") {
    const comparison = currentRnnComparisons[Number(metricIndex) || 0];
    if (comparison) {
      svg = buildRnnBarChartSvg({
        title: `${comparison.metricConfig?.label || "Metric"} - ${t("rnn.evaluation.runComparison")}`,
        rows: (comparison.rows || []).filter((row) => row.hasValue)
      });
      filename = `rnn-${String(comparison.metricConfig?.label || "comparison").toLowerCase().replace(/[^a-z0-9]+/g, "-")}.svg`;
    }
  } else if (kind === "diagnostic") {
    svg = buildRnnDiagnosticSvg(currentRnnEvaluationDashboard.diagnostic || {});
    filename = currentRnnEvaluationDashboard.diagnostic?.type === "confusion"
      ? "rnn-confusion-matrix.svg"
      : "rnn-residual-diagnostic.svg";
  }
  if (!svg) {
    eventBus.emit("toast", t("rnn.evaluation.downloadUnavailable"));
    return;
  }
  const blob = new Blob([svg], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
  eventBus.emit("toast", t("rnn.evaluation.downloadedSvg", { filename }));
}

function resolveRnnComparisonMetricKeys(metricSchema = {}) {
  const metricKeys = [
    ...(metricSchema.groups?.quality || []).map(metricKeyFromSchemaKey),
    "val_loss"
  ].filter(Boolean);
  const uniqueKeys = [...new Set(metricKeys)];
  if (uniqueKeys.includes("mae")) {
    return ["mae", "rmse", "val_loss"].filter((key) => uniqueKeys.includes(key));
  }
  const classificationDefaults = ["accuracy", "macro_f1", "val_loss"].filter((key) => uniqueKeys.includes(key));
  return (classificationDefaults.length ? classificationDefaults : uniqueKeys).slice(0, 3);
}

function metricKeyFromSchemaKey(schemaKey = "") {
  const mapping = {
    "val/accuracy": "accuracy",
    "val/macro_f1": "macro_f1",
    "val/precision": "precision",
    "val/recall": "recall",
    "val/mae": "mae",
    "val/rmse": "rmse",
    "val/loss": "val_loss"
  };
  return mapping[schemaKey] || "";
}

function renderRnnBaselineComparison(metricSchema = {}) {
  const container = qs("#rnn-eval-run-comparison-chart-grid");
  const countBadge = qs("#rnn-eval-run-comparison-count");
  if (!container) return;
  const metricKeys = resolveRnnComparisonMetricKeys(metricSchema);
  const comparisons = metricKeys.map((metricKey) => buildRnnBaselineComparisonViewModel({
    runs: trainingModeState.rnn.evaluationRuns || [],
    metricsByRun: trainingModeState.rnn.evaluationRunMetrics || {},
    metricKey
  }));
  currentRnnComparisons = comparisons;
  setText("#rnn-eval-run-comparison-count", t("rnn.evaluation.metricCount", { count: comparisons.length }));
  countBadge?.classList.toggle("hidden", !comparisons.length);
  renderRnnRunComparisonCharts(comparisons);
}

function renderRnnLineChart(canvasId, emptyId, chartModel = {}, variant = "score") {
  const canvas = qs(`#${canvasId}`);
  const empty = qs(`#${emptyId}`);
  if (!canvas) return;
  const hasSeries = Array.isArray(chartModel.series)
    && chartModel.series.some((item) => (item.values || []).some((value) => typeof value === "number" && Number.isFinite(value)));
  empty?.classList.toggle("hidden", hasSeries);
  canvas.classList.toggle("hidden", !hasSeries);
  const chartRef = canvasId === "rnn-eval-score-chart" ? rnnScoreChart : rnnLossChart;
  if (chartRef) chartRef.destroy();
  if (typeof Chart !== "undefined" && typeof Chart.getChart === "function") {
    Chart.getChart(canvas)?.destroy();
  }
  if (!hasSeries || typeof Chart === "undefined") {
    if (canvasId === "rnn-eval-score-chart") rnnScoreChart = null;
    if (canvasId === "rnn-eval-loss-chart") rnnLossChart = null;
    return;
  }
  const palette = variant === "loss"
    ? ["#ef4444", "#f59e0b", "#a855f7", "#14b8a6"]
    : ["#3b82f6", "#22c55e", "#a855f7", "#f59e0b"];
  const datasets = chartModel.series.map((series, index) => ({
    label: series.label,
    data: series.values,
    borderColor: palette[index % palette.length],
    backgroundColor: palette[index % palette.length],
    tension: 0.28,
    pointRadius: 2,
    spanGaps: false,
    borderWidth: 2.2
  }));
  const chart = new Chart(canvas, {
    type: "line",
    data: { labels: chartModel.labels || [], datasets },
    options: buildRnnChartOptions(variant === "loss" ? "Loss" : "Epoch Score")
  });
  if (canvasId === "rnn-eval-score-chart") rnnScoreChart = chart;
  if (canvasId === "rnn-eval-loss-chart") rnnLossChart = chart;
}

function renderRnnRunComparisonCharts(comparisons = []) {
  const host = qs("#rnn-eval-run-comparison-chart-grid");
  if (!host) return;
  rnnRunComparisonCharts.forEach((chart) => chart.destroy());
  rnnRunComparisonCharts = [];

  const available = comparisons.filter((comparison) => (comparison.rows || []).some((row) => row.hasValue));
  currentRnnComparisons = available;
  if (!available.length) {
    host.innerHTML = `<div class="rnn-eval-chart-empty">${escapeHtml(t("rnn.evaluation.noComparableRuns"))}</div>`;
    return;
  }

  host.innerHTML = available.map((comparison, index) => {
    const label = comparison.metricConfig?.label || "Metric";
    const hint = comparison.metricConfig?.hint || "";
    return `
      <div class="rnn-comparison-card">
        <div class="rnn-comparison-card-head">
          <div><strong>${escapeHtml(label)}</strong><span>${escapeHtml(hint)}</span></div>
          <button type="button" class="btn btn-secondary btn-sm" data-rnn-chart-download="comparison" data-metric-index="${index}"><i class="fa-solid fa-download"></i> SVG</button>
        </div>
        <canvas id="rnn-eval-run-comparison-chart-${index}"></canvas>
      </div>
    `;
  }).join("");

  if (typeof Chart === "undefined") return;
  available.forEach((comparison, index) => {
    const canvas = qs(`#rnn-eval-run-comparison-chart-${index}`);
    const rows = (comparison.rows || []).filter((row) => row.hasValue);
    if (!canvas || !rows.length) return;
    rnnRunComparisonCharts.push(new Chart(canvas, {
      type: "bar",
      data: {
        labels: rows.map((row) => row.label),
        datasets: [{
          label: comparison.metricConfig?.label || "Metric",
          data: rows.map((row) => row.value),
          backgroundColor: rows.map((_, rowIndex) => ["#3b82f6", "#22c55e", "#f59e0b", "#a855f7"][rowIndex % 4]),
          borderWidth: 0,
          borderRadius: 4,
          maxBarThickness: 48
        }]
      },
      options: buildRnnChartOptions(comparison.metricConfig?.label || "Metric", { compact: true })
    }));
  });
}

function buildRnnChartOptions(yTitle, { compact = false } = {}) {
  const isLight = document.body.dataset.theme === "light";
  const gridColor = isLight ? "#e2e8f0" : "rgba(148, 163, 184, 0.16)";
  const textColor = isLight ? "#475569" : "#cbd5e1";
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: !compact, labels: { color: textColor, font: { family: "Inter", size: 11 } } },
      tooltip: { mode: "index", intersect: false }
    },
    scales: {
      x: {
        grid: { color: gridColor },
        ticks: { color: textColor, font: { family: "Inter", size: compact ? 10 : 12 } },
        title: { display: !compact, text: "Epoch / Run", color: textColor }
      },
      y: {
        grid: { color: gridColor },
        ticks: { color: textColor, font: { family: "Inter", size: compact ? 10 : 12 } },
        title: { display: !compact, text: yTitle, color: textColor }
      }
    }
  };
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
  const statusView = resolveRnnEvaluationSidebarStatusRender(sidebar);
  const statusBadge = qs(statusView.selector);
  if (statusBadge) {
    statusBadge.className = statusView.className;
    statusBadge.textContent = statusView.text;
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

async function loadRnnExportModels(options = {}) {
  if (!appState.currentProjectId) {
    trainingModeState.rnn.exportModels = [];
    trainingModeState.rnn.exportArtifacts = [];
    trainingModeState.rnn.exportProjectId = "";
    trainingModeState.rnn.exportLoaded = false;
    renderRnnExportPanel();
    return;
  }
  if (trainingModeState.rnn.exportLoading && !options.force) {
    renderRnnExportPanel();
    return;
  }
  if (!options.force
    && trainingModeState.rnn.exportProjectId === appState.currentProjectId
    && trainingModeState.rnn.exportLoaded) {
    renderRnnExportPanel();
    return;
  }

  trainingModeState.rnn.exportLoading = true;
  trainingModeState.rnn.exportProjectId = appState.currentProjectId;
  renderRnnExportPanel();
  try {
    const models = await apiFetch(`/api/projects/${appState.currentProjectId}/models?scope=all`);
    trainingModeState.rnn.exportModels = filterRnnInferenceModels(models, trainingModeState.rnn.backend);
    await loadRnnExportArtifacts();
    trainingModeState.rnn.exportLoaded = true;
  } catch (err) {
    trainingModeState.rnn.exportModels = [];
    trainingModeState.rnn.exportArtifacts = [];
    trainingModeState.rnn.exportLoaded = false;
    eventBus.emit("toast", t("export.toast.failed", { message: err.message }));
  } finally {
    trainingModeState.rnn.exportLoading = false;
    renderRnnExportPanel();
  }
}

async function loadRnnExportArtifacts() {
  if (!appState.currentProjectId) {
    trainingModeState.rnn.exportArtifacts = [];
    return;
  }
  try {
    const payload = await apiFetch(`/api/projects/${appState.currentProjectId}/exports?limit=8`);
    trainingModeState.rnn.exportArtifacts = Array.isArray(payload?.exports) ? payload.exports : [];
  } catch (err) {
    console.error("Failed to load RNN export artifacts", err);
    trainingModeState.rnn.exportArtifacts = [];
  }
}

function renderRnnExportPanel() {
  const select = qs("#rnn-export-model");
  const badge = qs("#rnn-export-status-badge");
  const result = qs("#rnn-export-result");
  const artifactList = qs("#rnn-export-artifact-list");
  const models = trainingModeState.rnn.exportModels || [];

  if (select) {
    const current = select.value;
    select.innerHTML = renderRnnExportModelOptions(models);
    if (!trainingModeState.rnn.exportLoading && models.length) {
      const values = models.map((model) => model.model_id);
      select.value = values.includes(current) ? current : values[0];
    }
  }

  if (badge) {
    const ready = Boolean(appState.currentProjectId && models.length && !trainingModeState.rnn.exportLoading);
    badge.className = `summary-badge ${ready ? "badge-success" : "badge-neutral"}`;
    badge.textContent = trainingModeState.rnn.exportLoading
      ? t("common.loading")
      : (ready ? t("rnn.export.ready") : t("rnn.export.waiting"));
  }

  if (result) {
    const last = trainingModeState.rnn.exportLastResult || trainingModeState.rnn.exportArtifacts?.[0];
    result.innerHTML = last
      ? renderRnnExportResult(last)
      : escapeHtml(t("rnn.export.noResult"));
  }
  if (artifactList) {
    artifactList.innerHTML = renderExportArtifactList(trainingModeState.rnn.exportArtifacts || []);
  }

  updateRnnExportControls();
}

function renderRnnExportModelOptions(models = []) {
  if (!appState.currentProjectId) {
    return `<option value="">${escapeHtml(t("rnn.export.selectProjectFirst"))}</option>`;
  }
  if (trainingModeState.rnn.exportLoading) {
    return `<option value="">${escapeHtml(t("common.loading"))}</option>`;
  }
  if (!models.length) {
    return `<option value="">${escapeHtml(t("rnn.export.noModels"))}</option>`;
  }
  return models.map((model) => {
    const runId = model.run_id || model.model_id || "run";
    const weightType = model.weight_type || "best";
    const backend = model.backend || model.task_type || "rnn";
    return `<option value="${escapeHtml(model.model_id)}">${escapeHtml(`${runId} / ${weightType} / ${backend}`)}</option>`;
  }).join("");
}

function updateRnnExportControls() {
  const select = qs("#rnn-export-model");
  const hasProject = Boolean(appState.currentProjectId);
  const hasModel = Boolean(select?.value || trainingModeState.rnn.exportModels?.length);
  const busy = trainingModeState.rnn.exportLoading || trainingModeState.rnn.exportRunning;
  const blocker = !hasProject ? t("actionGuard.reason.project") : !hasModel ? t("rnn.export.noModels") : "";
  qsa("[data-rnn-export-format]").forEach((button) => {
    button.disabled = busy;
    button.dataset.requires = blocker && !busy ? "custom" : "";
    button.dataset.blockReason = blocker && !busy ? blocker : "";
    button.setAttribute("aria-disabled", blocker || busy ? "true" : "false");
    button.closest(".control-card")?.classList.toggle("muted", Boolean(blocker || busy));
  });
  const refresh = qs("#rnn-refresh-export-models");
  if (refresh) {
    refresh.disabled = trainingModeState.rnn.exportLoading;
    refresh.dataset.requires = !hasProject && !trainingModeState.rnn.exportLoading ? "project" : "";
  }
}

async function exportRnnArtifact(format = "rnn_package") {
  if (!appState.currentProjectId) {
    eventBus.emit("toast", t("export.selectProjectFirst"));
    return;
  }
  const selectedModelId = qs("#rnn-export-model")?.value || "";
  if (!selectedModelId && !(trainingModeState.rnn.exportModels || []).length) {
    eventBus.emit("toast", t("rnn.export.noModels"));
    return;
  }

  const params = new URLSearchParams({ format });
  if (selectedModelId) params.set("model_id", selectedModelId);
  trainingModeState.rnn.exportRunning = true;
  renderRnnExportPanel();
  const task = beginTask({ kind: "export", title: t("task.export.title"), stage: t("task.export.preparing"), method: "POST" });
  try {
    eventBus.emit("toast", t("export.toast.running"));
    const launch = await apiFetch(`/api/projects/${appState.currentProjectId}/export/jobs?${params.toString()}`, {
      method: "POST",
      suppressProgress: true,
    });
    const data = await followServerTask(launch.job_id, { controller: task, kind: "export", title: t("task.export.title") });
    trainingModeState.rnn.exportLastResult = data;
    await loadRnnExportArtifacts();
    renderRnnExportPanel();
    eventBus.emit("toast", t("export.toast.done", { path: resolveExportPath(data) }));
  } catch (err) {
    task.fail({ message: err.message });
    eventBus.emit("toast", t("export.toast.failed", { message: err.message }));
  } finally {
    trainingModeState.rnn.exportRunning = false;
    renderRnnExportPanel();
  }
}

function renderRnnExportResult(result = {}) {
  const rows = [
    [t("rnn.export.resultType"), result.export_type || "rnn_export"],
    [t("rnn.export.resultRun"), result.run_id || "--"],
    [t("rnn.export.resultPath"), resolveExportPath(result)],
    [t("rnn.export.resultCreated"), result.created_at || "--"]
  ];
  return `
    <div class="rnn-export-result-card">
      ${rows.map(([label, value]) => `
        <div class="summary-row">
          <span>${escapeHtml(label)}</span>
          <code>${escapeHtml(String(value || "--"))}</code>
        </div>
      `).join("")}
    </div>
  `;
}

function resolveExportPath(data = {}) {
  return data.package_abs_path
    || data.contract_abs_path
    || data.onnx_abs_path
    || data.pt_abs_path
    || data.package_path
    || data.contract_path
    || data.onnx_path
    || data.pt_path
    || "exported";
}

async function loadRnnInferenceModels(options = {}) {
  if (!appState.currentProjectId || (trainingModeState.rnn.inferenceLoading && !options.force)) {
    renderRnnInferenceModels();
    return;
  }
  const projectChanged = trainingModeState.rnn.inferenceProjectId !== appState.currentProjectId;
  if (!options.force && !projectChanged && trainingModeState.rnn.inferenceModelsLoaded) {
    renderRnnInferenceModels();
    return;
  }

  trainingModeState.rnn.inferenceLoading = true;
  trainingModeState.rnn.inferenceProjectId = appState.currentProjectId;
  renderRnnInferenceModels();
  try {
    const models = await apiFetch(`/api/projects/${appState.currentProjectId}/models?scope=all`);
    trainingModeState.rnn.inferenceModels = filterRnnInferenceModels(models, trainingModeState.rnn.backend);
    trainingModeState.rnn.inferenceModelsLoaded = true;
  } catch (err) {
    trainingModeState.rnn.inferenceModels = [];
    trainingModeState.rnn.inferenceModelsLoaded = false;
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
    const launch = await apiUpload(`/api/projects/${appState.currentProjectId}/inference/sequence/jobs`, {
      method: "POST",
      body: form
    });
    const result = await followServerTask(launch.job_id, { kind: "inference", title: t("task.inference.title") });
    trainingModeState.rnn.inferenceResult = result;
    trainingModeState.rnn.inferenceResultLoaded = true;
    trainingModeState.rnn.inferenceResultProjectId = appState.currentProjectId;
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

async function loadLatestRnnInferenceResult(options = {}) {
  if (!appState.currentProjectId) {
    trainingModeState.rnn.inferenceResult = null;
    trainingModeState.rnn.inferenceResultLoaded = false;
    trainingModeState.rnn.inferenceResultProjectId = "";
    renderRnnInferenceResult();
    return;
  }
  const projectChanged = trainingModeState.rnn.inferenceResultProjectId !== appState.currentProjectId;
  if (!projectChanged && trainingModeState.rnn.inferenceResultLoaded && !options.force) {
    renderRnnInferenceResult();
    return;
  }

  const container = qs("#rnn-inference-result");
  if (container && options.force) {
    container.textContent = t("rnn.inference.loadingLatest");
  }

  try {
    const payload = await apiFetch(`/api/projects/${appState.currentProjectId}/inference/jobs`, { suppressToast: true });
    const jobs = Array.isArray(payload?.jobs) ? payload.jobs : [];
    trainingModeState.rnn.inferenceResultProjectId = appState.currentProjectId;
    trainingModeState.rnn.inferenceResultLoaded = true;
    const latest = jobs.find((job) =>
      job?.kind === "sequence" || job?.mode === "rnn" || job?.architecture === "rnn"
    );
    if (!latest?.job_id) {
      if (options.force) trainingModeState.rnn.inferenceResult = null;
      renderRnnInferenceResult();
      return;
    }
    const detail = await apiFetch(`/api/projects/${appState.currentProjectId}/inference/jobs/${encodeURIComponent(latest.job_id)}`, {
      suppressToast: true
    });
    trainingModeState.rnn.inferenceResult = normalizeRnnInferenceJobResult(detail);
    renderRnnInferenceResult();
  } catch (err) {
    trainingModeState.rnn.inferenceResultLoaded = false;
    if (options.force) eventBus.emit("toast", `Failed to load sequence inference result: ${err.message}`);
    renderRnnInferenceResult();
  }
}

function normalizeRnnInferenceJobResult(job = {}) {
  const files = Array.isArray(job.files) ? job.files : [];
  const urlFor = (name) => files.find((file) => file.name === name)?.url || "";
  return {
    job_id: job.job_id,
    model: {
      model_id: job.model_id,
      run_id: job.run_id,
      backend: job.backend,
      task_type: job.task_type,
      architecture: job.architecture
    },
    summary: {
      ...(job.summary || {}),
      sequence_count: job.summary?.sequence_count ?? job.sequence_count,
      inference_time_ms: job.summary?.inference_time_ms ?? job.inference_time_ms,
      created_at: job.summary?.created_at ?? job.created_at,
      run_id: job.summary?.run_id ?? job.run_id
    },
    predictions: Array.isArray(job.predictions)
      ? job.predictions
      : (Array.isArray(job.prediction?.predictions) ? job.prediction.predictions : []),
    urls: {
      prediction_json: urlFor("prediction.json"),
      prediction_csv: urlFor("predictions.csv"),
      summary_json: urlFor("summary.json")
    }
  };
}

function renderRnnInferenceResult() {
  const container = qs("#rnn-inference-result");
  const result = trainingModeState.rnn.inferenceResult;
  if (!container) return;
  if (!result) {
    container.textContent = t("rnn.inference.noResult");
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
    trainingModeState.rnn.modelGuides = await apiFetch("/static/data/model_guide_catalog.json", { cache: "no-store" });
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
  const featureTaskHead = qs("#rnn-feature-task-head");
  const backend = qs("#rnn-backend");
  const infoIcon = qs("#rnn-model-info-icon");
  if (model === "xgboost_classifier" && taskHead) taskHead.value = "classification";
  if (model === "xgboost_regressor" && taskHead) taskHead.value = "regression";
  if (featureTaskHead && taskHead) featureTaskHead.value = taskHead.value || featureTaskHead.value;
  if (backend) {
    backend.value = selectedRnnBackendDisplay(entry, model);
  }
  if (infoIcon) {
    const tooltipKey = `rnn.modelTooltip.${model}`;
    const fallback = RNN_MODEL_TOOLTIPS[model] || entry?.display_name || t("rnn.modelTooltip.default");
    infoIcon.dataset.tooltip = t(tooltipKey) === tooltipKey ? fallback : t(tooltipKey);
    infoIcon.dataset.i18nTooltip = tooltipKey;
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

function syncRnnAdvancedParameterControls() {
  const customLearningRate = qs("#rnn-lr-mode")?.value === "custom";
  qs("#rnn-learning-rate")?.classList.toggle("hidden", !customLearningRate);
  qs("#rnn-lr-auto-hint")?.classList.toggle("hidden", customLearningRate);
  const model = String(qs("#rnn-model-family")?.value || "").toLowerCase();
  const backend = String(qs("#rnn-backend")?.value || "").toLowerCase();
  const isTreeModel = model.includes("xgboost") || backend.includes("xgboost");
  qsa("[data-rnn-neural-only]").forEach((field) => field.classList.toggle("hidden", isTreeModel));
  qs("#rnn-advanced-applicability-note")?.classList.toggle("hidden", !isTreeModel);
  const earlyStopEnabled = Boolean(qs("#rnn-early-stop-enabled")?.checked);
  qs("#rnn-patience-field")?.classList.toggle("hidden", !earlyStopEnabled);
  const patience = Math.max(1, Number(qs("#rnn-early-stopping-patience")?.value || 10));
  setText("#rnn-patience-summary", earlyStopEnabled
    ? t("rnn.training.patienceSummary", { count: patience })
    : t("rnn.training.earlyStopDisabled"));
  renderRnnTrainingAdjustmentSummary();
}

function renderRnnTrainingAdjustmentSummary() {
  const entry = getSelectedRnnModelEntry();
  const model = String(qs("#rnn-model-family")?.value || "").toLowerCase();
  const backend = String(qs("#rnn-backend")?.value || "").toLowerCase();
  const isTreeModel = model.includes("xgboost") || backend.includes("xgboost");
  const modelName = entry?.display_name || qs("#rnn-model-family")?.selectedOptions?.[0]?.textContent || "--";
  setText("#rnn-summary-model", modelName);
  setText("#rnn-summary-model-note", getSelectedRnnTaskHead() === "regression"
    ? t("rnn.training.regressionSummary")
    : t("rnn.training.classificationSummary"));
  if (isTreeModel) {
    setText("#rnn-estimated-memory", t("rnn.training.treeResourceEstimate"));
  } else {
    const hidden = Math.max(1, Number(qs("#rnn-hidden-size")?.value || 128));
    const layers = Math.max(1, Number(qs("#rnn-layers")?.value || 2));
    const batch = Math.max(1, Number(qs("#rnn-batch-size")?.value || 16));
    const estimatedMb = Math.max(256, Math.round((hidden * layers * batch * 0.45 + 384) / 64) * 64);
    setText("#rnn-estimated-memory", estimatedMb >= 1024 ? `${(estimatedMb / 1024).toFixed(1)} GB` : `${estimatedMb} MB`);
  }
  setText("#rnn-estimated-epoch-time", t("rnn.training.estimatePending"));
}

function canStartRnnTraining() {
  return canStartRnnTrainingFromState({
    hasProject: Boolean(appState.currentProjectId),
    modelTrainable: isSelectedRnnModelTrainable(),
    readiness: trainingModeState.rnn.readiness,
    readinessLoading: trainingModeState.rnn.readinessLoading || trainingModeState.rnn.configLoading,
    trainingStarting: trainingModeState.rnn.trainingStarting,
    trainingStatus: appState.trainingStatus?.status || ""
  });
}

function updateRnnStartControls() {
  const canStart = canStartRnnTraining();
  const message = getRnnStartBlockerMessage();
  const titleMessage = message === "Open a project before starting RNN training."
    ? t("rnn.training.openProjectFirst")
    : message;
  const buttons = [qs("#rnn-start-disabled")].filter(Boolean);
  buttons.forEach((button) => {
    const operationBusy = trainingModeState.rnn.trainingStarting || ["training", "running", "stopping"].includes(String(appState.trainingStatus?.status || "").toLowerCase());
    button.disabled = operationBusy;
    button.removeAttribute("data-requires");
    delete button.dataset.blockReason;
    button.setAttribute("aria-disabled", operationBusy ? "true" : "false");
    button.classList.add("btn-primary");
    button.classList.toggle("is-busy", operationBusy);
    button.title = canStart ? t("rnn.training.startTitle") : titleMessage;
  });

  const bannerBtn = qs("#rnn-start-disabled");
  if (bannerBtn) {
    bannerBtn.innerHTML = renderRnnStartBannerButtonContent(canStart);
  }
  const guidance = qs("#rnn-training-start-guidance");
  if (guidance) {
    guidance.className = `rnn-start-guidance ${canStart ? "is-ready" : "is-warning"}`;
    guidance.innerHTML = canStart
      ? `<i class="fa-solid fa-circle-check"></i><span>${escapeHtml(t("rnn.training.readyGuidance"))}</span>`
      : `<i class="fa-solid fa-triangle-exclamation"></i><span>${escapeHtml(titleMessage)}</span>`;
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
    readinessLoading: trainingModeState.rnn.readinessLoading || trainingModeState.rnn.configLoading,
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
    eventBus.emit("toast", t("rnn.training.started"));
    eventBus.emit("start-training-monitor");
    eventBus.emit("refresh-project");
  } catch (err) {
    eventBus.emit("toast", t("rnn.training.startFailed", { message: err.message }));
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
    learningRateMode: qs("#rnn-lr-mode")?.value || "auto",
    learningRate: qs("#rnn-learning-rate")?.value,
    optimizer: qs("#rnn-optimizer")?.value || "auto",
    hiddenSize: qs("#rnn-hidden-size")?.value,
    layers: qs("#rnn-layers")?.value,
    dropout: qs("#rnn-dropout")?.value,
    gradientClipNorm: qs("#rnn-gradient-clip")?.value,
    earlyStopEnabled: Boolean(qs("#rnn-early-stop-enabled")?.checked),
    earlyStoppingPatience: qs("#rnn-early-stopping-patience")?.value
  };
}

