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
    readinessLoading: false,
    trainingStarting: false,
    inferenceModels: [],
    inferenceLoading: false,
    inferenceRunning: false,
    inferenceResult: null
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
      loadRnnReadiness();
      if (trainingModeState.activeRnnPanel === "sequence-test") loadRnnInferenceModels();
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
    button.addEventListener("click", () => {
      qsa("[data-mode-nav]").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      if (button.dataset.modeNav === "overview") {
        trainingModeState.activeCnnPanel = "overview";
        trainingModeState.activeRnnPanel = "overview";
        eventBus.emit("navigate", trainingModeState.activeMode === "cnn" ? "dashboard" : "training");
        renderTrainingModeSidebar();
        renderTrainingWorkspace();
        if (trainingModeState.activeMode === "rnn") loadRnnReadiness();
      }
    });
  });

  initRnnPreviewEvents();
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
  if (mode === "rnn") loadRnnReadiness();
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
}

export function initRnnPreviewEvents() {
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
    qs(selector)?.addEventListener("change", () => loadRnnReadiness({ force: true }));
  });
  ["#rnn-start-disabled", "#rnn-training-disabled-action"].forEach((selector) => {
    qs(selector)?.addEventListener("click", startRnnTraining);
  });
  qs("#rnn-refresh-models")?.addEventListener("click", () => loadRnnInferenceModels({ force: true }));
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
    setText("#rnn-readiness-message", loading ? "Checking sequence manifest and CSV feature files..." : "RNN readiness checks only inspect sequence_manifest.json and CSV feature files.");
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
  setText("#rnn-readiness-message", readiness.message || "RNN readiness preview is available.");
  setText("#rnn-readiness-mode-badge", canStart ? "Training enabled" : "CSV required");
  setText("#rnn-sequence-dataset-message", canStart
    ? `${sequenceCount} sequence(s) detected from CSV. RNN training can start.`
    : `${sequenceCount} sequence(s) detected. RNNBackend MVP requires CSV feature sequence readiness before training.`);
  setText("#rnn-sequence-dataset-preview", source === "none" ? "sequence_id, timestep, feature_1, feature_2, target" : `source=${source}, feature_dim=${featureDim}, split=${splitText}`);
  updateRnnStartControls();

  const list = qs("#rnn-readiness-checks");
  if (list) {
    list.innerHTML = (readiness.checks || []).map((check) => {
      const statusClass = check.status === "pass" ? "success" : check.status === "warning" ? "warning" : "danger";
      return `<li class="rnn-readiness-item ${statusClass}">
        <strong>${escapeHtml(check.label || check.key)}</strong>
        <span>${escapeHtml(check.message || "")}</span>
      </li>`;
    }).join("");
  }
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
    if (models.some((model) => model.model_id === current)) select.value = current;
  }
  updateRnnInferenceControls();
}

function updateRnnInferenceControls() {
  const btn = qs("#rnn-run-sequence-inference");
  const reason = qs("#rnn-inference-reason");
  if (!btn) return;
  const message = getRnnInferenceBlockerMessage();
  const canRun = !message;
  btn.disabled = !canRun;
  btn.classList.toggle("btn-primary", canRun);
  btn.classList.toggle("btn-disabled", !canRun);
  if (reason) reason.textContent = message || "Ready to run CSV sequence inference.";
}

function getRnnInferenceBlockerMessage() {
  if (!appState.currentProjectId) return "Open a project before sequence inference.";
  if (trainingModeState.rnn.inferenceLoading) return "Loading RNN models.";
  if (trainingModeState.rnn.inferenceRunning) return "Sequence inference is running.";
  if (!qs("#rnn-inference-model")?.value) return "Select an RNN model.";
  const hasFile = Boolean(qs("#rnn-inference-csv-file")?.files?.[0]);
  const hasPath = Boolean(qs("#rnn-inference-csv-path")?.value?.trim());
  if (!hasFile && !hasPath) return "Provide a CSV feature sequence file or project CSV path.";
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
  form.append("device", qs("#rnn-inference-device")?.value || "cpu");
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

function canStartRnnTraining() {
  const readiness = trainingModeState.rnn.readiness;
  const csv = readiness?.summary?.csv || {};
  const trainState = appState.trainingStatus || {};
  const isRunning = trainState.status === "training" || trainState.status === "stopping";
  return Boolean(
    appState.currentProjectId &&
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
    stateBadge.textContent = canStart ? "Training enabled" : "Readiness required";
  }
}

function getRnnStartBlockerMessage() {
  if (!appState.currentProjectId) return "Open a project before starting RNN training.";
  if (trainingModeState.rnn.readinessLoading) return "RNN readiness is still checking.";
  if (trainingModeState.rnn.trainingStarting) return "RNN training is starting.";
  const trainState = appState.trainingStatus || {};
  if (trainState.status === "training" || trainState.status === "stopping") return "Another training job is already active.";
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
  const model = qs("#rnn-model-family")?.value || "lstm";
  const taskHead = qs("#rnn-task-head")?.value || "classification";
  const configData = {
    backend: trainingModeState.rnn.backend,
    model,
    epochs: Number(qs("#rnn-epochs")?.value || 10),
    batch_size: Number(qs("#rnn-batch-size")?.value || 16),
    imgsz: 320,
    lr0: 0.001,
    device: qs("#rnn-device")?.value || "cpu",
    sequence_length: Number(qs("#rnn-sequence-length")?.value || 16),
    stride: Number(qs("#rnn-stride")?.value || 8),
    horizon: Number(qs("#rnn-horizon")?.value || 1),
    task_head: taskHead,
    hidden_size: Number(qs("#rnn-hidden-size")?.value || 128),
    num_layers: Number(qs("#rnn-layers")?.value || 2),
    dropout: Number(qs("#rnn-dropout")?.value || 0.2),
    bidirectional: model === "bilstm"
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
