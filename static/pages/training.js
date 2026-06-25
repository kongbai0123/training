import { eventBus } from "../event_bus.js";
import { appState, getProjectStatus } from "../state.js";
import { apiFetch } from "../api.js";
import { qs, qsa, setText, setHTML, escapeHtml } from "../utils.js";

// Chart.js 實例與資料快取
let metricsChart = null;
let currentChartData = null; // 當前繪圖用的數據
let activeChartTab = "primary"; // 當前選取的 Chart Tab

function setMetricsDashboardActive(active) {
  qs("#training-metrics-empty")?.classList.toggle("hidden", active);
  qs("#training-metrics-active")?.classList.toggle("hidden", !active);
}

export function initTraining() {
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

  qs("#btn-start-train")?.addEventListener("click", async () => {
    const status = getProjectStatus(appState.currentProject);
    const blockers = getTrainingBlockers(status);
    const modelName = qs("#train-model")?.value || "";
    const taskType = String(status.taskType || "").toLowerCase();
    const isSegTask = taskType.includes("segmentation") || taskType.includes("seg");
    const isSegModel = modelName.includes("-seg");

    if (isSegTask && !isSegModel) {
      eventBus.emit("toast", "This project is segmentation. Please select a segmentation model.");
      return;
    }

    if (blockers.length > 0) {
      eventBus.emit("toast", "Training is blocked. Fix readiness blockers first.");
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

      eventBus.emit("toast", "Training started.");
      startMonitorWebSocket();
      eventBus.emit("refresh-project");
    } catch (err) {
      eventBus.emit("toast", `Failed to start training: ${err.message}`);
    }
  });

  qs("#btn-stop-train")?.addEventListener("click", async () => {
    try {
      await apiFetch(`/api/projects/${appState.currentProjectId}/train/stop`, { method: "POST" });
      eventBus.emit("toast", "Stop request sent. Waiting for training process to exit.");
    } catch (err) {
      eventBus.emit("toast", `Failed to stop training: ${err.message}`);
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
}

export function renderTrainingMonitor() {
  const status = getProjectStatus(appState.currentProject);
  const trainState = appState.trainingStatus || {};
  const blockers = getTrainingBlockers(status);
  const isReady = blockers.length === 0;
  const isRunning = trainState.status === "training";
  const isStopping = trainState.status === "stopping";
  const hasMetrics = isRunning || Boolean(currentChartData?.epochs?.length);

  setText("#card-ds-total", status.hasProject ? `${status.imageCount} images` : "--");
  setText("#card-ds-split", status.hasProject ? `Images: ${status.imageCount}` : "Images: --");
  setText("#card-ann-status", status.hasProject ? `${status.annotationRate}%` : "--");
  setText("#card-ann-detail", status.hasProject ? `Annotated: ${status.annotatedCount} / Missing: ${status.unannotatedCount}` : "Annotated: --");
  setText("#card-split-status", status.splitComplete ? "Ready" : "Missing");
  setText("#card-split-detail", status.hasProject ? `Train / Val / Test: ${status.splitCounts.train} / ${status.splitCounts.val} / ${status.splitCounts.test}` : "Train / Val / Test: --");
  setText("#card-model-name", status.hasProject ? (qs("#train-model")?.value || "--") : "--");
  setText("#card-model-task", status.hasProject ? `Task: ${status.taskType || "--"}` : "Task: --");

  const hw = trainState.hardware || {};
  const gpu = hw.gpu || {};
  setText("#card-hw-device", gpu.available ? gpu.name : "CPU mode");
  setText("#card-hw-vram", gpu.available ? `VRAM: ${gpu.vram_total} MB` : "VRAM: --");

  const currentRunId = trainState.run_id || appState.currentProject?.training_config?.run_id || "--";
  setText("#card-run-id", currentRunId);
  setText("#card-run-status", `Status: ${trainState.status || "Idle"}`);

  updateTelemetryProgress("#tel-cpu-val", "#tel-cpu-bar", hw.cpu_usage);
  updateTelemetryProgress("#tel-ram-val", "#tel-ram-bar", hw.ram_used !== undefined && hw.ram_total ? (hw.ram_used / hw.ram_total) * 100 : undefined, hw.ram_used && hw.ram_total ? `${hw.ram_used} / ${hw.ram_total} MB` : "");
  updateTelemetryProgress("#tel-gpu-val", "#tel-gpu-bar", gpu.available ? gpu.usage : undefined);
  updateTelemetryProgress("#tel-vram-val", "#tel-vram-bar", gpu.available ? (gpu.vram_used / gpu.vram_total) * 100 : undefined, gpu.available ? `${gpu.vram_used} / ${gpu.vram_total} MB` : "");

  const startBtn = qs("#btn-start-train");
  const stopBtn = qs("#btn-stop-train");
  const lockMsg = qs("#config-lock-msg");
  const configForm = qs("#form-training-config");
  const startBlocker = qs("#training-start-blocker");
  const shouldLockConfig = !isReady || isRunning || isStopping;

  if (startBtn) {
    startBtn.disabled = shouldLockConfig;
    startBtn.title = shouldLockConfig ? "Training is blocked until readiness checks pass." : "Start training";
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
      ? "Training configuration is locked while a run is active."
      : isStopping
        ? "Training is stopping. Configuration remains locked."
        : "Training configuration is locked until Dataset, LabelMe annotations, and Split are ready.";
    lockMsg.querySelector("span") && (lockMsg.querySelector("span").textContent = message);
  }

  if (configForm) {
    qsa("#form-training-config input, #form-training-config select").forEach((el) => {
      el.disabled = shouldLockConfig;
    });
  }
  if (startBlocker) {
    startBlocker.classList.toggle("hidden", isReady);
    startBlocker.innerHTML = isReady ? "" : `<strong>Start Training is disabled.</strong><ul>${blockers.map((b) => `<li>${escapeHtml(b.text)}</li>`).join("")}</ul>`;
  }

  renderReadinessGuard(status, blockers);
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
    
    // 設定預設模型 (分割任務強制使用 -seg 模型)
    const modelSelect = qs("#train-model");
    if (modelSelect) {
      modelSelect.value = data.model;
    }
    
    // 設定其他推薦超參數
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

// Readiness Guard 渲染
function getTrainingBlockers(status) {
  const blockers = [];
  const modelName = qs("#train-model")?.value || "";
  const taskType = String(status.taskType || "").toLowerCase();
  const isSegTask = taskType.includes("segmentation") || taskType.includes("seg");
  const isSegModel = modelName.includes("-seg");

  if (!status.hasProject) {
    blockers.push({ text: "No project is currently opened.", action: "Create or open a project.", nav: "dashboard" });
    return blockers;
  }
  if (!status.hasDataset || status.imageCount === 0) {
    blockers.push({ text: "No dataset images found.", action: "Import images in Dataset.", nav: "dataset" });
  }
  if (!status.labelme?.synced) {
    blockers.push({ text: "LabelMe annotations have not been synced.", action: "Sync annotations in LabelMe.", nav: "labelme" });
  }
  if (!status.splitComplete) {
    blockers.push({ text: "Train / Val / Test split is missing.", action: "Create a split before training.", nav: "split" });
  }
  if (isSegTask && !isSegModel) {
    blockers.push({ text: "Selected model is not compatible with segmentation training.", action: "Choose a segmentation model.", nav: null });
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
        <div><i class="fa-solid fa-triangle-exclamation"></i> Training Readiness: Blocked</div>
        <span class="summary-badge badge-danger">${blockers.length} blocker${blockers.length > 1 ? "s" : ""}</span>
      </div>
      <p>Fix these items before editing training settings or starting a run.</p>
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
      <div><i class="fa-solid fa-circle-check"></i> Training Readiness: Ready</div>
      <span class="summary-badge badge-success">Ready</span>
    </div>
    <p>Dataset, LabelMe annotations, split, model compatibility, and basic hardware checks are ready for training.</p>
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
    el.textContent = "Open a project before generating training recommendations.";
    return;
  }
  if (!gpu?.available) {
    el.textContent = "GPU is not available. CPU mode is safer, but training will be slow.";
    return;
  }

  let risk = "Low";
  let advice = "Current settings look reasonable.";
  if (vramMb && vramMb < 8000 && (batch >= 8 || imgsz >= 768)) {
    risk = "High";
    advice = "Recommended: batch 4, image size 640.";
  } else if (vramMb && vramMb < 12000 && (batch >= 16 || imgsz >= 768 || model.includes("m-seg"))) {
    risk = "Medium";
    advice = "Recommended: batch 8, image size 640 for segmentation stability.";
  }
  el.textContent = `VRAM risk: ${risk}. ${advice}`;
}

function updateTelemetryProgress(textSelector, barSelector, value, customText = "") {
  const textEl = qs(textSelector);
  const barEl = qs(barSelector);
  if (!textEl || !barEl) return;

  if (value === undefined || isNaN(value)) {
    textEl.textContent = "--";
    barEl.style.width = "0%";
    barEl.className = "bar";
    return;
  }

  const intVal = Math.round(value);
  textEl.textContent = customText || `${intVal}%`;
  barEl.style.width = `${intVal}%`;
  
  // 級距顏色樣式
  if (intVal < 70) {
    barEl.className = "bar normal";
  } else if (intVal < 90) {
    barEl.className = "bar warning";
  } else {
    barEl.className = "bar danger";
  }
}

// 載入最近一次 Run 的 Metrics 指標重繪
let lastLoadedRunId = null;
async function loadLatestRunMetricsOnce() {
  if (!appState.currentProjectId) return;
  
  // 取得最新 Run
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
    
    // 如果最近一個 run 的 id 改變了，重新讀取 metrics
    const latestRun = runs[0];
    if (latestRun.run_id === lastLoadedRunId && currentChartData) {
      return; // 已經載入過，不重複發送請求
    }
    
    await loadRunMetrics(latestRun.run_id);
  } catch (err) {
    console.error("loadLatestRunMetricsOnce error", err);
    setMetricsDashboardActive(false);
  }
}

// 載入特定 run 指標與 artifacts
async function loadRunMetrics(runId) {
  try {
    const data = await apiFetch(`/api/projects/${appState.currentProjectId}/train/runs/${runId}/metrics`);
    currentChartData = data;
    lastLoadedRunId = runId;
    setMetricsDashboardActive(Boolean(data?.epochs?.length));
    
    // 更新圖表與 Epoch 表格
    updateChartVisualization();
    renderEpochHistoryTable(currentChartData);
    
    // 更新 Trend Diagnostic UI
    updateTrendDiagnostic(runId);
    
    // 讀取該 run 的 artifacts
    await loadRunArtifacts(runId);
  } catch (err) {
    console.error("loadRunMetrics error", err);
    currentChartData = null;
    updateChartVisualization();
    renderEpochHistoryTable(null);
    setMetricsDashboardActive(false);
  }
}

// 載入特定 run 的 artifacts
async function loadRunArtifacts(runId) {
  try {
    const data = await apiFetch(`/api/projects/${appState.currentProjectId}/train/runs/${runId}/artifacts`);
    renderArtifactList(data, runId);
  } catch (err) {
    console.error("loadRunArtifacts error", err);
    renderArtifactList(null, runId);
  }
}

// 渲染 Trend Diagnostic 資訊
async function updateTrendDiagnostic(runId) {
  try {
    const runs = await apiFetch(`/api/projects/${appState.currentProjectId}/train/runs`);
    const run = runs.find(r => r.run_id === runId);
    if (!run || !run.health) {
      setText("#trend-best-epoch", "--");
      setText("#trend-platform-score", "--");
      setHTML("#trend-suggestions", "尚無診斷數據。");
      qs("#trend-health-badge").className = "status-badge Good";
      qs("#trend-health-badge").textContent = "Good";
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
    
    const suggs = health.suggestions || [];
    setHTML("#trend-suggestions", suggs.map(s => `<div>• ${escapeHtml(s)}</div>`).join(""));
  } catch (err) {
    console.error("updateTrendDiagnostic error", err);
  }
}

// 繪製 Chart.js 圖表
function updateChartVisualization() {
  const canvas = qs("#metrics-chart-canvas");
  if (!canvas) return;

  if (metricsChart) {
    metricsChart.destroy();
    metricsChart = null;
  }

  if (!currentChartData || !currentChartData.epochs || currentChartData.epochs.length === 0) {
    // 繪製空的 Canvas 背景
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#95a1b1";
    ctx.font = "14px Inter";
    ctx.textAlign = "center";
    ctx.fillText("尚無可用指標數據繪圖", canvas.width / 2, canvas.height / 2);
    return;
  }

  const epochs = currentChartData.epochs;
  const showRaw = qs("#chart-show-raw")?.checked !== false;
  const showSmooth = qs("#chart-show-smooth")?.checked !== false;
  const alpha = Number(qs("#chart-ema-alpha")?.value || 0.25);

  const datasets = [];
  const raw = currentChartData.raw || {};
  
  // 計算 EMA (EMA 前端動態平滑)
  const computeEma = (arr) => {
    if (!arr || arr.length === 0) return [];
    const ema = [];
    let curr = arr[0];
    for (const val of arr) {
      curr = alpha * val + (1 - alpha) * curr;
      ema.append ? ema.push(curr) : ema.push(curr); // 防禦性寫法
    }
    return ema;
  };

  // 根據 tab-btn 名稱選擇指標
  let keysToRender = [];
  let colors = {
    primary1: { raw: "rgba(59, 130, 246, 0.4)", smooth: "#3b82f6" }, // mAP50-95
    primary2: { raw: "rgba(16, 185, 129, 0.4)", smooth: "#10b981" }, // mAP50
    loss1: { raw: "rgba(239, 68, 68, 0.4)", smooth: "#ef4444" }, // box loss
    loss2: { raw: "rgba(245, 158, 11, 0.4)", smooth: "#f59e0b" }, // seg loss
    loss3: { raw: "rgba(139, 92, 246, 0.4)", smooth: "#8b5cf6" }, // cls loss
  };

  if (activeChartTab === "primary") {
    // 優先尋找 Segmentation Mask 指標，再 Fallback Box 指標
    const map50_95_key = "metrics/mAP50-95(M)" in raw ? "metrics/mAP50-95(M)" : "metrics/mAP50-95(B)";
    const map50_key = "metrics/mAP50(M)" in raw ? "metrics/mAP50(M)" : "metrics/mAP50(B)";
    
    keysToRender = [
      { key: map50_95_key, label: "mAP50-95", color: colors.primary1 },
      { key: map50_key, label: "mAP50", color: colors.primary2 }
    ];
  } else if (activeChartTab === "loss") {
    // 找出所有 Loss
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

// 點擊 Report View 更新 results.png 靜態圖片路徑
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

// 渲染 Epoch History 表格
function renderEpochHistoryTable(data) {
  const tbody = qs("#epoch-history-rows");
  if (!tbody) return;

  if (!data || !data.epochs || data.epochs.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding:16px; color:var(--text-muted);">尚無訓練歷史。</td></tr>`;
    return;
  }

  const epochs = data.epochs;
  const raw = data.raw || {};
  
  // 決定主 mAP 列顯示
  const mAP50_key = "metrics/mAP50(M)" in raw ? "metrics/mAP50(M)" : "metrics/mAP50(B)";
  const mAP50_95_key = "metrics/mAP50-95(M)" in raw ? "metrics/mAP50-95(M)" : "metrics/mAP50-95(B)";
  const prec_key = "metrics/precision(M)" in raw ? "metrics/precision(M)" : "metrics/precision(B)";
  const rec_key = "metrics/recall(M)" in raw ? "metrics/recall(M)" : "metrics/recall(B)";
  const loss_key = "train/box_loss" in raw ? "train/box_loss" : "train/seg_loss";

  const rows = [];
  // 降序呈現 Epoch 數
  for (let i = epochs.length - 1; i >= 0; i--) {
    const ep = epochs[i];
    const loss = raw[loss_key] ? Number(raw[loss_key][i]).toFixed(4) : "--";
    const map50 = raw[mAP50_key] ? Number(raw[mAP50_key][i]).toFixed(3) : "--";
    const map50_95 = raw[mAP50_95_key] ? Number(raw[mAP50_95_key][i]).toFixed(3) : "--";
    const precision = raw[prec_key] ? Number(raw[prec_key][i]).toFixed(3) : "--";
    const recall = raw[rec_key] ? Number(raw[rec_key][i]).toFixed(3) : "--";

    rows.push(`
      <tr>
        <td><strong>${ep}</strong></td>
        <td><code>${loss}</code></td>
        <td>${map50}</td>
        <td>${map50_95}</td>
        <td>${precision}</td>
        <td>${recall}</td>
        <td><span class="badge badge-success">Completed</span></td>
      </tr>
    `);
  }

  tbody.innerHTML = rows.join("");
}

// 渲染 Artifact 清單
function renderArtifactList(artifacts, runId) {
  const container = qs("#artifact-list-container");
  if (!container) return;

  if (!artifacts || artifacts.length === 0) {
    container.innerHTML = `<div class="empty-state">此 Run 尚無產生任何實體檔案成果。</div>`;
    return;
  }

  const rows = artifacts.map((art) => {
    const filename = art.filename;
    const sizeKb = (art.size / 1024).toFixed(1);
    const downloadUrl = `/api/projects/${appState.currentProjectId}/train/runs/${runId}/artifacts/download/${filename}?path=${encodeURIComponent(art.rel_path)}`;
    
    let actions = `
      <a href="${downloadUrl}" class="btn btn-secondary btn-sm" target="_blank" download>
        <i class="fa-solid fa-download"></i> 下載
      </a>
    `;

    // 額外支持 weights/best.pt 匯出 ONNX
    if (filename === "best.pt") {
      actions += `
        <button class="btn btn-primary btn-sm" onclick="exportArtifactOnnx('${runId}')" style="margin-left: 6px;">
          <i class="fa-solid fa-file-export"></i> 匯出 ONNX
        </button>
      `;
    }

    return `
      <div class="artifact-row">
        <div class="art-info">
          <span>${escapeHtml(filename)}</span>
          <small>Size: ${sizeKb} KB | Path: ${escapeHtml(art.rel_path)}</small>
        </div>
        <div style="display:flex; align-items:center;">
          ${actions}
        </div>
      </div>
    `;
  });

  container.innerHTML = rows.join("");
}

// 匯出 ONNX 全域函式綁定
window.exportArtifactOnnx = async function(runId) {
  eventBus.emit("toast", "正在將 best.pt 模型轉換並匯出成 ONNX 格式...");
  try {
    const res = await apiFetch(`/api/projects/${appState.currentProjectId}/train/runs/${runId}/export-onnx`, { method: "POST" });
    if (res.success) {
      eventBus.emit("toast", "ONNX 模型已成功匯出，並備份至 exports 目錄！");
      // 重新加載檔案清單
      await loadRunArtifacts(runId);
    }
  } catch (err) {
    eventBus.emit("toast", `ONNX 匯出失敗：${err.message}`);
  }
};

// 渲染 Run History 歷史紀錄表格
async function renderRunHistoryTable() {
  const tbody = qs("#run-history-rows");
  if (!tbody) return;

  if (!appState.currentProjectId) {
    tbody.innerHTML = `<tr><td colspan="10" class="text-center" style="padding:16px; color:var(--text-muted);">尚未有歷史運行紀錄。</td></tr>`;
    return;
  }

  try {
    const runs = await apiFetch(`/api/projects/${appState.currentProjectId}/train/runs`);
    if (!runs || runs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="10" class="text-center" style="padding:16px; color:var(--text-muted);">尚未有歷史運行紀錄。</td></tr>`;
      return;
    }

    const rows = runs.map((run) => {
      const runId = run.run_id;
      const date = run.completed_at ? new Date(run.completed_at).toLocaleString() : "--";
      const config = run.best_metrics || {};
      
      const runTaskType = String(run.task_type || "").toLowerCase();
      const isSeg = runTaskType.includes("segmentation") || runTaskType.includes("seg");
      const suffix = isSeg ? "(M)" : "(B)";
      
      const mAP50 = config[`metrics/mAP50${suffix}`] !== undefined ? Number(config[`metrics/mAP50${suffix}`]).toFixed(3) : "--";
      const mAP50_95 = config[`metrics/mAP50-95${suffix}`] !== undefined ? Number(config[`metrics/mAP50-95${suffix}`]).toFixed(3) : "--";
      
      let statusBadge = `<span class="badge badge-success">Completed</span>`;
      if (run.status === "failed") {
        statusBadge = `<span class="badge badge-danger">Failed</span>`;
      } else if (run.status === "stopped") {
        statusBadge = `<span class="badge badge-warning">Stopped</span>`;
      } else if (run.status === "training") {
        statusBadge = `<span class="badge badge-success fa-spin"><i class="fa-solid fa-spinner"></i> Running</span>`;
      }

      return `
        <tr data-run-id="${escapeHtml(runId)}" class="${runId === lastLoadedRunId ? "row-success" : ""}" style="cursor:pointer;">
          <td><code>${escapeHtml(runId)}</code></td>
          <td>${date}</td>
          <td>${escapeHtml(run.model || "--")}</td>
          <td>${run.epochs || "--"}</td>
          <td>${run.imgsz || "--"}</td>
          <td>${run.batch_size || "--"}</td>
          <td>${mAP50}</td>
          <td>${mAP50_95}</td>
          <td>${statusBadge}</td>
          <td>
            <button class="btn btn-secondary btn-sm btn-view-run" data-run-id="${escapeHtml(runId)}">
              <i class="fa-solid fa-chart-line"></i> View
            </button>
          </td>
        </tr>
      `;
    });

    tbody.innerHTML = rows.join("");

    // 綁定歷史行點擊與「View」載入
    qsa("#run-history-rows tr").forEach((row) => {
      const runId = row.dataset.runId;
      row.querySelector(".btn-view-run")?.addEventListener("click", async (e) => {
        e.stopPropagation();
        await selectRunIdAndRender(runId);
      });
      row.addEventListener("click", async () => {
        await selectRunIdAndRender(runId);
      });
    });

  } catch (err) {
    console.error("renderRunHistoryTable error", err);
    tbody.innerHTML = `<tr><td colspan="10" class="text-center" style="padding:16px; color:var(--text-danger);">讀取運行歷史失敗。</td></tr>`;
  }
}

// 切換選擇 Run
async function selectRunIdAndRender(runId) {
  eventBus.emit("toast", `正在載入 ${runId} 的訓練數據...`);
  await loadRunMetrics(runId);
  
  // 重新渲染歷史表格的 highlight
  qsa("#run-history-rows tr").forEach((row) => {
    row.classList.toggle("row-success", row.dataset.runId === runId);
  });
}

// WebSocket 監聽即時訓練進度
function startMonitorWebSocket() {
  if (!appState.currentProjectId) return;
  
  // 防重複建立連線
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
    
    // 即時渲染進度與テレメトリー
    renderTrainingMonitor();
    
    // 全域事件更新通知
    eventBus.emit("state-changed");
    
    // 如果狀態不是 training，關閉 websocket 連線
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
    eventBus.emit("toast", "訓練即時監控連線 WebSocket 發生錯誤。");
    appState.wsConn = null;
  };
}
