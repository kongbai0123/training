import { eventBus } from "../event_bus.js";
import { appState, getProjectStatus, t } from "../state.js";
import { apiFetch } from "../api.js";
import { qs, qsa, setText, setHTML, escapeHtml } from "../utils.js";
import { initTrainingModeSidebar } from "./training_modes.js";

// Training UI helper
let metricsChart = null;
let currentChartData = null; // Training UI helper
let activeChartTab = "primary"; // Training UI helper

function setMetricsDashboardActive(active) {
  qs("#training-metrics-empty")?.classList.toggle("hidden", active);
  qs("#training-metrics-active")?.classList.toggle("hidden", !active);
}

export function initTraining() {
  initTrainingModeSidebar();

  qs("#tab-config-simple")?.addEventListener("click", () => {
    qs("#tab-config-simple").className = "btn btn-sm btn-primary";
    qs("#tab-config-advanced").className = "btn btn-sm btn-secondary";
    qs("#config-advanced-fields")?.classList.add("hidden");
  });
  qs("#tab-config-advanced")?.addEventListener("click", () => {
    qs("#tab-config-simple").className = "btn btn-sm btn-secondary";
    qs("#tab-config-advanced").className = "btn btn-sm btn-primary";
    qs("#config-advanced-fields")?.classList.remove("hidden");
  });

  qs("#btn-auto-recommend")?.addEventListener("click", loadRecommendedConfig);
  ["#train-model", "#train-batch", "#train-imgsz", "#train-device", "#train-profile"].forEach((selector) => {
    qs(selector)?.addEventListener("change", () => renderTrainingMonitor());
  });
  qs("#btn-training-open-model-hub")?.addEventListener("click", () => {
    eventBus.emit("toast", t("training.modelRegistry.hubPending"));
  });

  qs("#btn-start-train")?.addEventListener("click", async () => {
    const status = getProjectStatus(appState.currentProject);
    const blockers = getTrainingBlockers(status);
    const modelName = qs("#train-model")?.value || "";
    const taskType = String(status.taskType || "").toLowerCase();
    const isSegTask = taskType.includes("segmentation") || taskType.includes("seg");
    const isSegModel = modelName.includes("-seg");

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

      await apiFetch(`/api/projects/${appState.currentProjectId}/train/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(configData)
      });

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
  eventBus.on("language-changed", () => renderTrainingMonitor());
}

export function renderTrainingMonitor() {
  const status = getProjectStatus(appState.currentProject);
  const trainState = appState.trainingStatus || {};
  const blockers = getTrainingBlockers(status);
  const isReady = blockers.length === 0;
  const isRunning = trainState.status === "training";
  const isStopping = trainState.status === "stopping";
  const hasMetrics = isRunning || Boolean(currentChartData?.epochs?.length);

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
  const lockMsg = qs("#config-lock-msg");
  const configForm = qs("#form-training-config");
  const startBlocker = qs("#training-start-blocker");
  const shouldLockConfig = !isReady || isRunning || isStopping;
  const configFields = ["#config-simple-fields", "#config-advanced-fields", "#training-vram-risk"];
  const configTabs = qs(".training-config-panel .config-tabs-nav");

  if (startBtn) {
    startBtn.disabled = shouldLockConfig;
    startBtn.title = shouldLockConfig ? t("training.toast.blocked") : t("training.start");
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

  if (lockMsg) {
    lockMsg.classList.toggle("hidden", !shouldLockConfig);
    const message = isRunning
      ? t("training.config.lockedRunning")
      : isStopping
        ? t("training.config.lockedStopping")
        : t("training.config.locked");
    lockMsg.querySelector("span") && (lockMsg.querySelector("span").textContent = message);
  }

  if (configForm) {
    qsa("#form-training-config input, #form-training-config select").forEach((el) => {
      el.disabled = shouldLockConfig;
    });
  }
  configFields.forEach((selector) => {
    const el = qs(selector);
    if (!el) return;
    if (selector === "#config-advanced-fields" && isReady && qs("#tab-config-advanced")?.classList.contains("btn-primary")) {
      el.classList.remove("hidden");
    } else if (selector === "#config-advanced-fields") {
      el.classList.add("hidden");
    } else {
      el.classList.toggle("hidden", !isReady);
    }
  });
  configTabs?.classList.toggle("hidden", !isReady);
  if (startBlocker) {
    startBlocker.classList.toggle("hidden", isReady);
    startBlocker.innerHTML = isReady ? "" : `<strong>${escapeHtml(t("training.startDisabled"))}</strong><ul>${blockers.map((b) => `<li>${escapeHtml(b.text)}</li>`).join("")}</ul>`;
  }

  renderReadinessGuard(status, blockers);
  updateTrainingModelRegistrySkeleton(status);
  updateTrainingRecommendation(status, gpu);

  const monitorEmpty = qs("#training-monitor-empty");
  const monitorActive = qs("#training-monitor-active");

  const showMonitor = isRunning || isStopping || trainState.status === "completed" || trainState.status === "failed";
  monitorEmpty?.classList.toggle("hidden", showMonitor);
  monitorActive?.classList.toggle("hidden", !showMonitor);


  setText("#train-status-label", trainState.status || "Idle");
  setText("#train-progress-text", showMonitor ? `Epoch ${trainState.epoch || 0} / ${trainState.total_epochs || "--"}` : "--");

  const lastMetrics = trainState.metrics && trainState.metrics.length ? trainState.metrics[trainState.metrics.length - 1] : {};
  setText("#monitor-map50", lastMetrics.map50 !== undefined ? Number(lastMetrics.map50).toFixed(3) : "--");
  setText("#monitor-map50-95", lastMetrics.map50_95 !== undefined ? Number(lastMetrics.map50_95).toFixed(3) : "--");
  setText("#monitor-loss", lastMetrics.loss !== undefined ? Number(lastMetrics.loss).toFixed(4) : "--");

  if (isRunning) {
    const wsEpochs = (trainState.metrics || []).map((m) => m.epoch);
    const wsLoss = (trainState.metrics || []).map((m) => m.loss);
    const wsMap50 = (trainState.metrics || []).map((m) => m.map50);
    const wsMap50_95 = (trainState.metrics || []).map((m) => m.map50_95);
    const wsPrecision = (trainState.metrics || []).map((m) => m.precision);
    const wsRecall = (trainState.metrics || []).map((m) => m.recall);

    currentChartData = {
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
    updateChartVisualization();
    renderEpochHistoryTable(currentChartData);
  } else {
    loadLatestRunMetricsOnce();
  }

  setMetricsDashboardActive(hasMetrics);

  renderRunHistoryTable();
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
  const taskEl = qs("#training-model-task");
  const nameEl = qs("#training-model-selected-name");
  const noteEl = qs("#training-model-compatibility");
  const taskType = String(status.taskType || "").toLowerCase();
  const isSegTask = taskType.includes("segmentation") || taskType.includes("seg");
  const isSegModel = modelName.includes("-seg");
  const modelTask = isSegModel
    ? t("training.modelRegistry.yoloV8Seg")
    : t("training.modelRegistry.yoloV8Det");
  const compatible = !isSegTask || isSegModel;

  setText("#training-model-selected-name", modelName);
  setText("#training-model-task", modelTask);
  if (nameEl) nameEl.title = modelName;
  if (taskEl) taskEl.title = modelTask;
  if (noteEl) {
    noteEl.textContent = compatible
      ? t("training.modelRegistry.compatible")
      : t("training.modelRegistry.incompatible");
    noteEl.classList.toggle("is-compatible", compatible);
    noteEl.classList.toggle("is-warning", !compatible);
  }
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
      updateChartVisualization();
      renderEpochHistoryTable(null);
      renderArtifactList(null);
      setMetricsDashboardActive(false);
      return;
    }
    
    // Training UI helper
    const latestRun = runs[0];
    if (latestRun.run_id === lastLoadedRunId && currentChartData) {
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
  try {
    const data = await apiFetch(`/api/projects/${appState.currentProjectId}/train/runs/${runId}/metrics`);
    currentChartData = data;
    lastLoadedRunId = runId;
    setMetricsDashboardActive(Boolean(data?.epochs?.length));
    
    // Training UI helper
    updateChartVisualization();
    renderEpochHistoryTable(currentChartData);
    
    // Training UI helper
    updateTrendDiagnostic(runId);
    
    // Training UI helper
    await loadRunArtifacts(runId);
  } catch (err) {
    console.error("loadRunMetrics error", err);
    currentChartData = null;
    updateChartVisualization();
    renderEpochHistoryTable(null);
    setMetricsDashboardActive(false);
  }
}

// Training UI helper
async function loadRunArtifacts(runId) {
  try {
    const data = await apiFetch(`/api/projects/${appState.currentProjectId}/train/runs/${runId}/artifacts`);
    renderArtifactList(data, runId);
  } catch (err) {
    console.error("loadRunArtifacts error", err);
    renderArtifactList(null, runId);
  }
}

// Training UI helper
async function updateTrendDiagnostic(runId) {
  try {
    const runs = await apiFetch(`/api/projects/${appState.currentProjectId}/train/runs`);
    const run = runs.find((item) => item.run_id === runId);
    if (!run || !run.health) {
      setText("#trend-best-epoch", "--");
      setText("#trend-platform-score", "--");
      setHTML("#trend-suggestions", escapeHtml(t("training.suggestions.empty")));
      const badge = qs("#trend-health-badge");
      if (badge) {
        badge.className = "status-badge Good";
        badge.textContent = "Good";
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
  const canvas = qs("#metrics-chart-canvas");
  if (!canvas) return;

  if (metricsChart) {
    metricsChart.destroy();
    metricsChart = null;
  }

  if (!currentChartData || !currentChartData.epochs || currentChartData.epochs.length === 0) {
    // Training UI helper
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#95a1b1";
    ctx.font = "14px Inter";
    ctx.textAlign = "center";
    ctx.fillText(t("training.metrics.emptyTitle"), canvas.width / 2, canvas.height / 2);
    return;
  }

  const epochs = currentChartData.epochs;
  const showRaw = qs("#chart-show-raw")?.checked !== false;
  const showSmooth = qs("#chart-show-smooth")?.checked !== false;
  const alpha = Number(qs("#chart-ema-alpha")?.value || 0.25);

  const datasets = [];
  const raw = currentChartData.raw || {};
  
  // Training UI helper
  const computeEma = (arr) => {
    if (!arr || arr.length === 0) return [];
    const ema = [];
    let curr = arr[0];
    for (const val of arr) {
      curr = alpha * val + (1 - alpha) * curr;
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
      { key: map50_key, label: "mAP50", color: colors.primary2 }
    ];
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

  keysToRender.forEach((item) => {
    const rawData = raw[item.key] || [];
    if (rawData.length === 0) return;

    if (showRaw) {
      datasets.push({
        label: `${item.label} (Raw)`,
        data: rawData,
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
        label: `${item.label} (Smooth)`,
        data: smoothData,
        borderColor: item.color.smooth,
        backgroundColor: "transparent",
        borderWidth: 2.5,
        pointRadius: 2,
        tension: 0.2
      });
    }
  });

  const isLight = document.body.dataset.theme === "light";
  const gridColor = isLight ? "#e2e8f0" : "#2b3441";
  const textColor = isLight ? "#5d6b7d" : "#95a1b1";

  metricsChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: epochs,
      datasets: datasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: { color: textColor, font: { family: "Inter", size: 11 } }
        },
        tooltip: {
          mode: "index",
          intersect: false
        }
      },
      scales: {
        x: {
          grid: { color: gridColor },
          ticks: { color: textColor, font: { family: "Inter" } },
          title: { display: true, text: "Epoch", color: textColor }
        },
        y: {
          grid: { color: gridColor },
          ticks: { color: textColor, font: { family: "Inter" } }
        }
      }
    }
  });
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
      resultsImg.src = "https://raw.githubusercontent.com/ultralytics/assets/main/yolov8/banner-yolov8.png";
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
    if (filename === "best.pt") {
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
      const isSeg = runTaskType.includes("segmentation") || runTaskType.includes("seg");
      const suffix = isSeg ? "(M)" : "(B)";
      const map50 = config[`metrics/mAP50${suffix}`] !== undefined ? Number(config[`metrics/mAP50${suffix}`]).toFixed(3) : "--";
      const map5095 = config[`metrics/mAP50-95${suffix}`] !== undefined ? Number(config[`metrics/mAP50-95${suffix}`]).toFixed(3) : "--";
      let statusBadge = `<span class="badge badge-success">Completed</span>`;
      if (run.status === "failed") statusBadge = `<span class="badge badge-danger">Failed</span>`;
      else if (run.status === "stopped") statusBadge = `<span class="badge badge-warning">Stopped</span>`;
      else if (run.status === "training") statusBadge = `<span class="badge badge-success fa-spin"><i class="fa-solid fa-spinner"></i> Running</span>`;
      return `<tr data-run-id="${escapeHtml(runId)}" class="${runId === lastLoadedRunId ? "row-success" : ""}" style="cursor:pointer;"><td><code>${escapeHtml(runId)}</code></td><td>${date}</td><td>${escapeHtml(run.model || "--")}</td><td>${run.epochs || "--"}</td><td>${run.imgsz || "--"}</td><td>${run.batch_size || "--"}</td><td>${map50}</td><td>${map5095}</td><td>${statusBadge}</td><td><button class="btn btn-secondary btn-sm btn-view-run" data-run-id="${escapeHtml(runId)}"><i class="fa-solid fa-chart-line"></i> View</button></td></tr>`;
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
  
  appState.wsConn.onmessage = (event) => {
    const data = JSON.parse(event.data);
    appState.trainingStatus = data;
    
    // Training UI helper
    renderTrainingMonitor();
    
    // Training UI helper
    eventBus.emit("state-changed");
    
    // Training UI helper
    if (data.status !== "training") {
      try {
        appState.wsConn.close();
      } catch (e) {}
      eventBus.emit("refresh-project");
    }
  };
  
  appState.wsConn.onclose = () => {
    appState.wsConn = null;
  };
  appState.wsConn.onerror = () => {
    eventBus.emit("toast", "Training monitor WebSocket failed.");
    appState.wsConn = null;
  };
}
