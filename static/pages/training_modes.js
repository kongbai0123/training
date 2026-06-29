import { eventBus } from "../event_bus.js";
import { appState } from "../state.js";
import { apiFetch } from "../api.js";
import { qs, qsa, escapeHtml, setText } from "../utils.js";

export const trainingModeState = {
  activeMode: "cnn",
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
    trainingStarting: false
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
      eventBus.emit("navigate", "training");
      renderTrainingModeSidebar();
      renderTrainingWorkspace();
      loadRnnReadiness();
    });
  });

  qsa("[data-cnn-nav]").forEach((button) => {
    button.addEventListener("click", () => {
      trainingModeState.activeMode = "cnn";
      renderTrainingModeSidebar();
      renderTrainingWorkspace();
    });
  });

  qsa("[data-mode-nav]").forEach((button) => {
    button.addEventListener("click", () => {
      qsa("[data-mode-nav]").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      if (button.dataset.modeNav === "overview") {
        trainingModeState.activeRnnPanel = "overview";
        eventBus.emit("navigate", "training");
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
  eventBus.emit("navigate", "training");
  renderTrainingModeSidebar();
  renderTrainingWorkspace();
  if (mode === "rnn") loadRnnReadiness();
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
    button.classList.toggle(
      "active",
      trainingModeState.activeMode === "cnn" && button.dataset.cnnNav === appState.currentPage
    );
  });

  qsa("[data-mode-nav]").forEach((button) => {
    button.classList.toggle(
      "active",
      button.dataset.modeNav === "overview"
        ? appState.currentPage === "training"
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

  qsa("[data-rnn-panel]").forEach((panel) => {
    const isActive = panel.dataset.rnnPanel === trainingModeState.activeRnnPanel;
    panel.classList.toggle("active", isActive);
  });

  renderRnnReadiness();
}

export function initRnnPreviewEvents() {
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
