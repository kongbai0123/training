// Vision Training Studio - Phase 1 Front-end Entry Module
import { eventBus } from "./event_bus.js";
import { 
  appState, 
  initPreferences, 
  applyLanguage, 
  updateLabelMeState, 
  getProjectStatus 
} from "./state.js";
import { apiFetch } from "./api.js";
import { 
  qs, 
  qsa, 
  setText, 
  setHTML, 
  escapeHtml 
} from "./utils.js";

// 載入頁面元件
import { initDashboard, renderDashboard } from "./pages/dashboard.js";
import { initProjects, renderProjectsPage } from "./pages/projects.js";
import { initDataset, renderDatasetPage } from "./pages/dataset.js";
import { initLabelMe, renderLabelMeManager } from "./pages/labelme.js";
import { initSplit, renderSplitPage } from "./pages/split.js";
import { initAugmentation, renderAugmentationPage } from "./pages/augmentation.js";
import { initTraining, renderTrainingMonitor, loadRecommendedConfig } from "./pages/training.js";
import { initEvaluation, renderEvaluationPage } from "./pages/evaluation.js";
import { initInference, renderInferencePage } from "./pages/inference.js";
import { initAutoLabeling, renderAutoLabelingPage } from "./pages/auto_labeling.js?v=20260624-auto-label-readable";
import { initExport, renderExportPage } from "./pages/export.js";
import { initSettings, renderSettingsPage } from "./pages/settings.js";

document.addEventListener("DOMContentLoaded", async () => {
  initPreferences();
  bindGlobalNavigation();
  bindInfoTooltips();
  
  // 載入硬體系統狀態（非阻塞，超時超控）
  fetchSystemHealth();

  // 初始化所有頁面
  initDashboard();
  initProjects();
  initDataset();
  initLabelMe();
  initSplit();
  initAugmentation();
  initTraining();
  initEvaluation();
  initInference();
  initAutoLabeling();
  initExport();
  initSettings();

  // 載入專案並預設跳轉到 Dashboard
  await loadProjects({ autoOpenLatest: true });
  navigate("dashboard");
});

async function fetchSystemHealth() {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 3500);

  try {
    const health = await apiFetch("/api/health", { signal: controller.signal });
    appState.systemHealth = health;
  } catch (err) {
    console.warn("Failed to fetch system health, using fallback:", err.message);
    appState.systemHealth = {
      status: "unhealthy",
      error: "Backend unavailable",
      device: { has_gpu: false, device_name: "Backend unavailable" }
    };
  } finally {
    clearTimeout(timeoutId);
    renderAll();
  }
}

// 全域導覽與事件訂閱
function bindInfoTooltips() {
  let tooltip = qs("#floating-tooltip");
  if (!tooltip) {
    tooltip = document.createElement("div");
    tooltip.id = "floating-tooltip";
    tooltip.className = "floating-tooltip";
    tooltip.setAttribute("role", "tooltip");
    document.body.appendChild(tooltip);
  }

  document.body.classList.add("tooltips-ready");

  const normalizeInfoIcons = () => {
    qsa(".info-icon[data-tooltip]").forEach((icon) => {
      if (!icon.hasAttribute("tabindex")) icon.setAttribute("tabindex", "0");
      if (!icon.hasAttribute("aria-label")) icon.setAttribute("aria-label", icon.dataset.tooltip);
    });
  };

  const renderTooltipContent = (text) => {
    const parts = String(text || "")
      .split(";")
      .map((part) => part.trim())
      .filter(Boolean);
    if (parts.length <= 1) return escapeHtml(parts[0] || "");
    const [title, ...items] = parts;
    return `
      <strong>${escapeHtml(title)}</strong>
      <ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    `;
  };

  const placeTooltip = (target) => {
    const rect = target.getBoundingClientRect();
    const margin = 12;
    const host = target.closest(".main-content")
      || target.closest(".right-summary-panel, .modal-content")
      || document.body;
    const hostRect = host === document.body
      ? { left: 0, right: window.innerWidth, top: 0, bottom: window.innerHeight }
      : host.getBoundingClientRect();
    const safeLeft = Math.max(margin, hostRect.left + margin);
    const safeRight = Math.min(window.innerWidth - margin, hostRect.right - margin);
    const safeTop = Math.max(margin, hostRect.top + margin);
    const safeBottom = Math.min(window.innerHeight - margin, hostRect.bottom - margin);
    const availableWidth = Math.max(220, safeRight - safeLeft);

    tooltip.classList.remove("place-right", "place-left");
    tooltip.style.maxWidth = `${availableWidth}px`;
    const tipRect = tooltip.getBoundingClientRect();
    const hostCenterX = hostRect.left + (hostRect.right - hostRect.left) / 2;
    const preferRight = rect.left + rect.width / 2 < hostCenterX;
    const rightLeft = rect.right + 10;
    const leftLeft = rect.left - tipRect.width - 10;
    let left = preferRight ? rightLeft : leftLeft;
    let top = rect.top + rect.height / 2 - tipRect.height / 2;

    if (preferRight && left + tipRect.width > safeRight) {
      left = leftLeft >= safeLeft ? leftLeft : safeRight - tipRect.width;
    }
    if (!preferRight && left < safeLeft) {
      left = rightLeft + tipRect.width <= safeRight ? rightLeft : safeLeft;
    }

    if (left < safeLeft) left = safeLeft;
    if (left + tipRect.width > safeRight) {
      left = safeRight - tipRect.width;
    }
    if (top < safeTop) top = safeTop;
    if (top + tipRect.height > safeBottom) {
      top = Math.max(safeTop, safeBottom - tipRect.height);
    }

    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
    tooltip.classList.add(left >= rect.right ? "place-right" : "place-left");
  };

  const showTooltip = (target) => {
    const text = target?.dataset?.tooltip;
    if (!text) return;
    tooltip.innerHTML = renderTooltipContent(text);
    tooltip.classList.add("is-visible");
    placeTooltip(target);
  };

  const hideTooltip = () => {
    tooltip.classList.remove("is-visible");
  };

  normalizeInfoIcons();
  new MutationObserver(normalizeInfoIcons).observe(document.body, { childList: true, subtree: true });

  document.addEventListener("mouseover", (event) => {
    const target = event.target.closest(".info-icon[data-tooltip]");
    if (target) showTooltip(target);
  });

  document.addEventListener("mouseout", (event) => {
    if (event.target.closest(".info-icon[data-tooltip]")) hideTooltip();
  });

  document.addEventListener("focusin", (event) => {
    const target = event.target.closest(".info-icon[data-tooltip]");
    if (target) showTooltip(target);
  });

  document.addEventListener("focusout", (event) => {
    if (event.target.closest(".info-icon[data-tooltip]")) hideTooltip();
  });

  document.addEventListener("click", (event) => {
    const target = event.target.closest(".info-icon[data-tooltip]");
    if (!target) return;
    event.preventDefault();
    event.stopPropagation();
    showTooltip(target);
  }, true);

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hideTooltip();
  });

  window.addEventListener("scroll", hideTooltip, true);
  window.addEventListener("resize", hideTooltip);
}

function bindGlobalNavigation() {
  qsa("[data-page]").forEach((btn) => {
    btn.addEventListener("click", () => navigate(btn.dataset.page));
  });
  
  document.addEventListener("click", (event) => {
    const navTarget = event.target.closest("[data-nav]");
    if (!navTarget) return;
    event.preventDefault();
    navigate(navTarget.dataset.nav);
  });

  // History Modal 觸發與關閉
  qs("#btn-header-history")?.addEventListener("click", openHistoryModal);
  qs("#btn-close-history")?.addEventListener("click", closeHistoryModal);
  qs("#project-history-modal")?.addEventListener("click", (event) => {
    if (event.target.id === "project-history-modal") closeHistoryModal();
  });

  // EventBus 事件監聽
  eventBus.on("state-changed", () => {
    renderAll();
  });

  eventBus.on("toast", (message) => {
    showToast(message);
  });

  eventBus.on("navigate", (pageId) => {
    navigate(pageId);
  });

  eventBus.on("open-project", async (projectId) => {
    await openProject(projectId, { page: "dashboard" });
  });

  eventBus.on("reload-projects", async (options = {}) => {
    await loadProjects({ autoOpenLatest: false });
    if (options.openProjectId) {
      await openProject(options.openProjectId, { page: "dashboard" });
    }
  });

  eventBus.on("refresh-project", async () => {
    await loadProjects({ autoOpenLatest: false });
    if (appState.currentProjectId) {
      await openProject(appState.currentProjectId, { stayOnPage: true });
    }
    showToast("狀態已重新整理");
  });

  eventBus.on("project-deleted", async (projectId) => {
    if (appState.currentProjectId === projectId) {
      appState.currentProjectId = null;
      appState.currentProject = null;
      appState.trainingStatus = null;
      updateLabelMeState();
      setText("#current-project-title", "尚未載入專案");
      if (appState.wsConn) {
        appState.wsConn.close();
        appState.wsConn = null;
      }
    }
    await loadProjects({ autoOpenLatest: false });
    renderAll();
  });
}

function navigate(pageId) {
  appState.currentPage = pageId || "dashboard";
  qsa(".sidebar-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.page === appState.currentPage);
  });
  qsa(".page").forEach((page) => {
    page.classList.toggle("active", page.id === `page-${appState.currentPage}`);
  });
  renderAll();
}

function renderAll() {
  const status = getProjectStatus(appState.currentProject);
  
  // 觸發各子頁面渲染
  renderDashboard(status);
  renderRightPanel(appState.currentPage, status);
  renderPageGuards(appState.currentPage, status);
  renderDatasetPage(status);
  renderLabelMeManager(status);
  renderSplitPage(status);
  renderAugmentationPage(status);
  renderTrainingMonitor();
  renderEvaluationPage(status);
  renderInferencePage(status);
  renderAutoLabelingPage(status);
  renderExportPage(status);
  renderSettingsPage();
  renderProjectsPage();

  updateActionAvailability(status);
  applyLanguage(appState.settings.language);
}

// 載入與開啟專案
async function loadProjects(options = {}) {
  try {
    appState.projects = await apiFetch("/api/projects");
    qs("#api-status-dot")?.classList.add("online");
    qs("#api-status-dot")?.classList.remove("offline");
    if (options.autoOpenLatest && !appState.currentProjectId && appState.projects.length > 0) {
      await openProject(appState.projects[0].project_id, { stayOnPage: true });
      return;
    }
    renderAll();
  } catch (err) {
    qs("#api-status-dot")?.classList.add("offline");
    showToast(`無法讀取專案清單：${err.message}`);
    renderAll();
  }
}

async function openProject(projectId, options = {}) {
  if (!projectId) return;
  try {
    appState.currentProject = await apiFetch(`/api/projects/${projectId}`);
    appState.currentProjectId = projectId;
    appState.currentProjectClasses = [...(appState.currentProject?.class_names || [])];
    setText("#current-project-title", appState.currentProject.project_name || projectId);
    updateLabelMeState();
    // 檢查並重設訓練 WebSocket
    await checkCurrentTrainStatus();
    // 載入該專案的模型清單
    try {
      const models = await apiFetch(`/api/projects/${projectId}/models`);
      appState.models = Array.isArray(models) ? models : [];
    } catch (e) {
      console.warn("Failed to prefetch models:", e.message);
      appState.models = [];
    }
    // 載入最推薦配置
    await loadRecommendedConfig();
    renderAll();
    if (!options.stayOnPage) navigate(options.page || "dashboard");
  } catch (err) {
    showToast(`無法載入專案：${err.message}`);
  }
}

async function checkCurrentTrainStatus() {
  if (!appState.currentProjectId) return;
  try {
    appState.trainingStatus = await apiFetch(`/api/projects/${appState.currentProjectId}/train/status`);
    // 觸發訓練 WebSocket 狀態監聽檢查
    eventBus.emit("check-training-websocket");
  } catch {
    appState.trainingStatus = null;
  }
}

// UI 面板渲染
function renderProjectSummary(status) {
  setHTML("#project-summary", `
    <div class="path-list">
      <div class="path-row"><span>Name</span><code>${escapeHtml(status.projectName)}</code></div>
      <div class="path-row"><span>Task</span><code>${escapeHtml(status.taskType)}</code></div>
      <div class="path-row"><span>Images</span><code>${status.imageCount}</code></div>
      <div class="path-row"><span>Annotated</span><code>${status.annotatedCount}/${status.imageCount}</code></div>
      <div class="path-row"><span>Split</span><code>${status.splitComplete ? "Ready" : "Not ready"}</code></div>
    </div>
  `);
}

// Dynamic Right Summary Panel Context Builders
const RIGHT_PANEL_CONFIG = {
  dashboard: buildDashboardRightPanel,
  projects: buildProjectsRightPanel,
  dataset: buildDatasetRightPanel,
  labelme: buildLabelMeRightPanel,
  split: buildSplitRightPanel,
  augmentation: buildAugmentationRightPanel,
  training: buildTrainingRightPanel,
  evaluation: buildEvaluationRightPanel,
  inference: buildInferenceRightPanel,
  "auto-labeling": buildAutoLabelingRightPanel,
  export: buildExportRightPanel,
  history: buildHistoryRightPanel,
  settings: buildSettingsRightPanel
};

// 統一的渲染引擎 (Separation of Concerns & XSS 防護)
function renderRightPanel(pageId, status) {
  // 1. 渲染精簡版專案全域摘要
  renderProjectSummary(status);

  // 2. 獲取頁面專屬的結構化 Context 資料
  const builder = RIGHT_PANEL_CONFIG[pageId];
  const container = qs("#page-context-container");
  const section = qs("#section-page-context");
  
  if (!container || !section) return;

  // 判定是否在無專案狀態下顯示 Empty State
  const bypassEmptyPages = ["dashboard", "projects", "settings"];
  const showEmpty = !status.hasProject && !bypassEmptyPages.includes(pageId);

  if (showEmpty) {
    section.style.display = "block";
    const titleEl = qs("#page-context-title");
    if (titleEl) titleEl.textContent = getPageTitle(pageId);
    
    container.innerHTML = `
      <div class="summary-empty">
        <p>Please create or open a project first.</p>
        <button class="btn btn-secondary btn-sm" data-nav="projects">Go to Projects</button>
      </div>
    `;
    
    // 渲染 Empty State 下的 Suggested Actions 與 Warnings
    setHTML("#next-actions-list", `<li>前往 <a href="#" data-nav="projects">Projects</a> 建立或開啟專案。</li>`);
    setHTML("#warning-list", `<div class="summary-warning-item">尚未載入專案，請先選擇專案。</div>`);
    return;
  }

  if (!builder) {
    section.style.display = "none";
    container.innerHTML = "";
    setHTML("#next-actions-list", "<li>目前沒有建議動作。</li>");
    setHTML("#warning-list", "");
    return;
  }

  // 取得計算後的結構化資料
  const config = builder(status);
  
  // 渲染 Context 標題
  const titleEl = qs("#page-context-title");
  if (titleEl && config.title) {
    titleEl.textContent = config.title;
  }

  // 3. 渲染 Page Context 內容 (XSS 安全 escape 處理)
  if (config.emptyState && !status.hasProject) {
    section.style.display = "block";
    container.innerHTML = `
      <div class="summary-empty">
        <p>${escapeHtml(config.emptyState.message)}</p>
        ${config.emptyState.actionLabel ? `<button class="btn btn-secondary btn-sm" data-nav="${escapeHtml(config.emptyState.actionNav)}">${escapeHtml(config.emptyState.actionLabel)}</button>` : ""}
      </div>
    `;
  } else {
    section.style.display = "block";
    const rowsHtml = (config.rows || []).map(row => {
      const valEsc = escapeHtml(row.value);
      let valDom = row.isCode ? `<code>${valEsc}</code>` : valEsc;
      if (row.badgeType) {
        valDom = `<span class="summary-badge badge-${row.badgeType}">${valDom}</span>`;
      }
      return `<div class="summary-row"><span>${escapeHtml(row.label)}</span>${valDom}</div>`;
    }).join("");
    container.innerHTML = rowsHtml ? `<div class="path-list" style="gap: 0;">${rowsHtml}</div>` : `<div class="summary-empty"><p>目前沒有可顯示的頁面資訊。</p></div>`;
  }

  // 4. 動態渲染 Next Suggested Actions (XSS 安全處理)
  const actions = config.actions || [];
  if (actions.length > 0) {
    setHTML("#next-actions-list", actions.map(act => `<li>${escapeHtml(act)}</li>`).join(""));
  } else {
    setHTML("#next-actions-list", "<li>目前沒有建議動作。</li>");
  }

  // 5. 動態渲染 Warnings (XSS 安全處理)
  const warnings = config.warnings || [];
  if (warnings.length > 0) {
    setHTML("#warning-list", warnings.map(warn => `<div class="summary-warning-item">${escapeHtml(warn)}</div>`).join(""));
  } else {
    setHTML("#warning-list", "");
  }
}

function getPageTitle(pageId) {
  const map = {
    dataset: "Dataset Status",
    labelme: "LabelMe Status",
    split: "Split Status",
    augmentation: "Augmentation Status",
    training: "Training Status",
    evaluation: "Evaluation Status",
    inference: "Inference Status",
    "auto-labeling": "Auto-Labeling Status",
    export: "Export Status",
    history: "History Status"
  };
  return map[pageId] || "Page Context";
}

function buildDashboardRightPanel(status) {
  const healthScore = status.hasDataset 
    ? Math.round((status.annotatedCount / status.imageCount) * 50 + (status.splitComplete ? 30 : 0) + (status.bestModelExists ? 20 : 0))
    : 0;

  const rows = status.hasProject ? [
    { label: "Health Score", value: `${healthScore}%`, badgeType: healthScore > 75 ? "success" : (healthScore > 40 ? "warning" : "danger") },
    { label: "Unannotated", value: String(status.unannotatedCount) },
    { label: "Best Model", value: status.bestModelExists ? "Exists" : "None", badgeType: status.bestModelExists ? "success" : "neutral" }
  ] : [];

  const actions = [];
  if (!status.hasProject) actions.push("前往 Projects 建立或載入專案。");
  else if (!status.hasDataset) actions.push("前往 Dataset 匯入圖片或影片。");
  else if (!status.labelme.synced) actions.push("前往 LabelMe 同步標註。");
  else if (!status.splitComplete) actions.push("前往 Split 切分資料集。");
  else actions.push("前往 Training 控制台進行模型訓練。");

  const warnings = [];
  if (!status.hasProject) warnings.push("尚未開啟任何專案，系統操作已限制。");
  else if (!status.hasDataset) warnings.push("專案中目前沒有影像資料。");

  return {
    title: "Dashboard Status",
    rows,
    actions,
    warnings,
    emptyState: !status.hasProject ? {
      message: "Please open a project on Projects page.",
      actionLabel: "Go to Projects",
      actionNav: "projects"
    } : null
  };
}

function buildProjectsRightPanel(status) {
  return {
    title: "Projects Status",
    rows: [
      { label: "Total Projects", value: String(appState.projects?.length || 0) }
    ],
    actions: ["在左方表單中填入名稱與類別，建立新專案。", "從歷程或列表中加載現有專案。"],
    warnings: appState.projects?.length === 0 ? ["系統目前沒有任何專案。"] : []
  };
}

function buildDatasetRightPanel(status) {
  const images = appState.currentProject?.images || [];
  const videos = new Set(images.map(img => img.source_video).filter(Boolean));
  const duplicates = images.filter(img => img.quality?.is_duplicate).length;
  const invalid = images.filter(img => img.quality?.is_corrupted).length;
  const score = status.hasDataset ? Math.max(0, 100 - (duplicates * 5) - (invalid * 10)) : 0;

  const actions = ["Run quality check 執行品質檢測", "Go to LabelMe 進行標記管理"];
  const warnings = [];
  if (duplicates > 0) warnings.push(`偵測到 ${duplicates} 張重疊/重複圖片，建議清理。`);
  if (invalid > 0) warnings.push(`偵測到 ${invalid} 張無效或損毀檔案。`);

  return {
    title: "Dataset Status",
    rows: [
      { label: "Raw images", value: String(status.imageCount) },
      { label: "Videos imported", value: String(videos.size) },
      { label: "Quality score", value: `${score}/100`, badgeType: score > 80 ? "success" : (score > 50 ? "warning" : "danger") },
      { label: "Duplicates", value: String(duplicates), badgeType: duplicates > 0 ? "warning" : null },
      { label: "Corrupted files", value: String(invalid), badgeType: invalid > 0 ? "danger" : null }
    ],
    actions,
    warnings
  };
}

function buildLabelMeRightPanel(status) {
  const lm = appState.labelme || {};
  const actions = ["Sync JSON 進行標籤同步", "Fix invalid labels 修正未知標籤"];
  const warnings = [];
  if (lm.missingJson > 0) warnings.push(`有 ${lm.missingJson} 張圖片尚未擁有 JSON 標記檔。`);
  if (lm.unknownLabels > 0) warnings.push(`偵測到 ${lm.unknownLabels} 個未在類別清單中的未知標籤。`);

  return {
    title: "LabelMe Status",
    rows: [
      { label: "JSON count", value: String(lm.jsonCount || 0) },
      { label: "Missing JSON", value: String(lm.missingJson || 0), badgeType: lm.missingJson > 0 ? "warning" : null },
      { label: "Invalid JSON", value: String(lm.invalidJson || 0), badgeType: lm.invalidJson > 0 ? "danger" : null },
      { label: "Unknown labels", value: String(lm.unknownLabels || 0), badgeType: lm.unknownLabels > 0 ? "danger" : null },
      { label: "Empty annotations", value: String(lm.emptyJson || 0) }
    ],
    actions,
    warnings
  };
}

function buildSplitRightPanel(status) {
  const actions = ["Review class balance 檢視類別平衡度", "Go to Augmentation 前往影像擴充"];
  const warnings = [];
  if (!status.splitComplete) warnings.push("尚未進行 Train / Val / Test 切分，將阻擋模型訓練！");
  if (status.splitCounts.val === 0) warnings.push("驗證集 (Val) 數量為 0，請務必分配驗證資料。");

  return {
    title: "Split Status",
    rows: [
      { label: "Train count", value: String(status.splitCounts.train) },
      { label: "Val count", value: String(status.splitCounts.val) },
      { label: "Test count", value: String(status.splitCounts.test) },
      { label: "Split quality score", value: `${status.splitQuality || 0}/100`, badgeType: status.splitQuality > 80 ? "success" : "neutral" },
      { label: "Leakage risk", value: status.splitComplete ? "Low" : "High", badgeType: status.splitComplete ? "success" : "danger" }
    ],
    actions,
    warnings
  };
}

function buildAugmentationRightPanel(status) {
  const multiplier = parseInt(qs("#aug-multiplier")?.value || qs("#multiplier")?.value || "3", 10);
  const activePresetBtn = qs(".preset-item.active");
  const presetName = activePresetBtn ? activePresetBtn.dataset.augPreset : "custom";
  const trainCount = status.splitCounts.train || 0;
  const valTestCount = (status.splitCounts.val || 0) + (status.splitCounts.test || 0);

  const actions = ["Preview augmentation 預覽擴增效果", "Apply to Train only 套用物理擴充", "Go to Training 前往模型訓練"];
  const warnings = ["Val/Test excluded (驗證與測試集不進行擴充)", "Strong blur may reduce annotation quality"];

  return {
    title: "Augmentation Status",
    rows: [
      { label: "Target", value: "Train only", isCode: true },
      { label: "Train images", value: String(trainCount) },
      { label: "Val/Test excluded", value: `Yes (${valTestCount})` },
      { label: "Multiplier", value: `x${multiplier}` },
      { label: "Estimated output", value: String(trainCount * multiplier), isCode: true },
      { label: "Current preset", value: presetName, isCode: true }
    ],
    actions,
    warnings
  };
}

function buildTrainingRightPanel(status) {
  const gpu = appState.systemHealth?.device?.device_name || "CPU";
  const model = qs("#train-model")?.value || "--";
  const runs = appState.currentProject?.training_runs || [];
  const latestRun = runs.length > 0 ? runs[runs.length - 1] : null;

  const formatNum = (v) => (v === null || v === undefined || v === "--") ? "--" : Number(v).toFixed(3);
  const runId = latestRun?.run_id ?? "--";
  const runStatus = latestRun?.status ?? "--";
  const bestMap = latestRun ? formatNum(latestRun.best_map50_95_m) : "--";
  const bestEpoch = latestRun ? String(latestRun.best_epoch ?? "--") : "--";

  // Badge colour for run status
  const statusBadge = runStatus === "completed" ? "success" : runStatus === "failed" ? "danger" : runStatus === "training" ? "warning" : "neutral";

  const actions = ["Fix readiness checks 排除阻擋因子", "Start training 啟動訓練流程", "View latest run 檢視運行指標"];
  const warnings = [];
  if (!status.trainReady) warnings.push("請排除阻擋因素（需有 Dataset、已同步 Label、已建立 Split）後才能啟動訓練。");
  if (gpu === "CPU" || gpu.includes("unavailable") || gpu.includes("Backend")) warnings.push("GPU unavailable (目前為 CPU 或無連線模式，訓練速度會極慢)。");

  return {
    title: "Training Status",
    rows: [
      { label: "Dataset ready", value: status.hasDataset ? "Yes" : "No", badgeType: status.hasDataset ? "success" : "danger" },
      { label: "Label ready", value: status.labelme.synced ? "Yes" : "No", badgeType: status.labelme.synced ? "success" : "danger" },
      { label: "Split ready", value: status.splitComplete ? "Yes" : "No", badgeType: status.splitComplete ? "success" : "danger" },
      { label: "Model", value: model },
      { label: "Hardware", value: gpu, isCode: true },
      { label: "Latest Run", value: runId, isCode: true },
      { label: "Run Status", value: runStatus, badgeType: statusBadge },
      { label: "Best Epoch", value: bestEpoch },
      { label: "Best mAP50-95", value: bestMap, isCode: true }
    ],
    actions,
    warnings
  };
}

function buildEvaluationRightPanel(status) {
  // Use appState.models as SSoT (populated by loadInferenceModels in inference.js)
  const models = appState.models || [];
  const model = models.find(m => m.weight_type === "best") || models[0];
  const formatNum = (v) => (v === null || v === undefined) ? "--" : Number(v).toFixed(3);

  return {
    title: "Evaluation Metrics",
    rows: [
      { label: "mAP50(M)", value: model ? formatNum(model.best_map50_m) : "--", isCode: true },
      { label: "mAP50-95(M)", value: model ? formatNum(model.best_map50_95_m) : "--", isCode: true },
      { label: "Precision(M)", value: model ? formatNum(model.precision) : "--" },
      { label: "Recall(M)", value: model ? formatNum(model.recall) : "--" },
      { label: "Model file", value: model ? model.weight_type : "--", isCode: true },
      { label: "Run ID", value: model?.run_id ?? "--", isCode: true }
    ],
    actions: ["與驗證標籤比對並生成 Confusion Matrix", "檢視預測失敗個案 (Failure cases)"],
    warnings: !status.bestModelExists ? ["目前尚未找到已訓練的最佳模型權重。"] : []
  };
}

function buildInferenceRightPanel(status) {
  // Use appState.models as SSoT; appState.inferenceSelectedModelId for selected model
  const models = appState.models || [];
  const bestCount = models.filter((m) => m.weight_type === "best").length;
  const lastCount = models.filter((m) => m.weight_type === "last").length;
  const latestRun = models.length > 0 ? (models[0]?.run_id ?? "--") : "--";

  // Resolve selected model display name from appState (not DOM)
  const selId = appState.inferenceSelectedModelId;
  const selModel = selId ? models.find((m) => m.model_id === selId) : null;
  const selectedModelName = selModel ? `${selModel.weight_type} (${selModel.run_id || "?"})` : "--";

  const actions = ["Select model 選擇載入權重", "Upload test image 上傳測試圖片", "Run inference 執行單張推論"];
  const warnings = [];
  if (models.length === 0) warnings.push("no trained weights found (尚未找到任何已訓練權重，請先訓練模型)。");

  return {
    title: "Model Registry",
    rows: [
      { label: "Models count", value: String(models.length) },
      { label: "best.pt count", value: String(bestCount) },
      { label: "last.pt count", value: String(lastCount) },
      { label: "Latest run", value: latestRun, isCode: true },
      { label: "Selected model", value: selectedModelName, isCode: true }
    ],
    actions,
    warnings
  };
}

function buildAutoLabelingRightPanel(status) {
  const models = appState.models || [];
  const compatibleModels = models.filter((model) => {
    const projectTask = String(status.taskType || "").toLowerCase();
    const modelTask = String(model.task_type || "").toLowerCase();
    if (!projectTask || !modelTask) return true;
    if (projectTask.includes("segmentation")) return modelTask.includes("segmentation");
    if (projectTask.includes("detection")) return modelTask.includes("detection");
    if (projectTask.includes("classification")) return modelTask.includes("classification");
    return true;
  });

  const actions = [
    "選擇 best.pt / last.pt 作為草稿產生模型。",
    "先用單張圖片 preview，再進入資料夾批次。",
    "後續 API 完成後，人工確認再 Export LabelMe / YOLO。"
  ];

  const warnings = [
    "P0 UI only：目前不會執行自動標註。",
    "Apply scope 預設為 Train only，避免污染 Val/Test。"
  ];
  if (models.length === 0) warnings.unshift("找不到可用模型，請先完成 Training。");
  if (models.length > 0 && compatibleModels.length === 0) warnings.unshift("目前模型任務與專案任務不相容。");

  return {
    title: "Auto-Labeling Status",
    rows: [
      { label: "UI status", value: "Phase UI", badgeType: "neutral" },
      { label: "Available models", value: String(models.length) },
      { label: "Compatible models", value: String(compatibleModels.length), badgeType: compatibleModels.length > 0 ? "success" : "warning" },
      { label: "Draft output", value: "LabelMe / YOLO", isCode: true },
      { label: "Apply scope", value: "Train only", badgeType: "warning" },
      { label: "Backend API", value: "Pending", badgeType: "neutral" }
    ],
    actions,
    warnings
  };
}

function buildExportRightPanel(status) {
  // Use appState.models as SSoT
  const models = appState.models || [];
  const bestModel = models.find((m) => m.weight_type === "best");
  return {
    title: "Export Status",
    rows: [
      { label: "Available weights", value: String(models.length) },
      { label: "Best run", value: bestModel?.run_id ?? "--", isCode: true },
      { label: "ONNX export", value: status.bestModelExists ? "Ready" : "Unavailable", badgeType: status.bestModelExists ? "success" : "neutral" },
      { label: "Report status", value: "Ready", badgeType: "success" }
    ],
    actions: ["Export ONNX 匯出跨平台部署格式", "Generate report 產生 Markdown 訓練報告"],
    warnings: !status.bestModelExists ? ["無最佳模型權重，ONNX 導出功能已停用。"] : []
  };
}

function buildHistoryRightPanel(status) {
  const runs = appState.currentProject?.training_runs?.length || 0;
  const imports = appState.currentProject?.imports_history?.length || 0;
  return {
    title: "History Status",
    rows: [
      { label: "Total runs", value: String(runs) },
      { label: "Imports count", value: String(imports) }
    ],
    actions: ["點選運行歷史記錄查看歷史 Metrics", "匯出專案變更歷程報告"],
    warnings: []
  };
}

function buildSettingsRightPanel(status) {
  const gpu = appState.systemHealth?.device?.device_name || "Backend unavailable";
  const path = status.datasetPath ? (status.datasetPath.length > 25 ? "..." + status.datasetPath.slice(-22) : status.datasetPath) : "--";
  const isHealthy = appState.systemHealth?.status === "healthy";
  return {
    title: "Settings Status",
    rows: [
      { label: "Dataset Path", value: path, isCode: true },
      { label: "Hardware Device", value: gpu },
      { label: "LabelMe Backend", value: status.labelme.backendReady ? "Connected" : "Disconnected", badgeType: status.labelme.backendReady ? "success" : "danger" },
      { label: "GPU/CPU status", value: isHealthy ? "Healthy" : "Offline", badgeType: isHealthy ? "success" : "danger" }
    ],
    actions: ["調整語言偏好設定", "切換深色/明亮主題亮度"],
    warnings: !isHealthy ? ["API 後端伺服器未連線或有超時異常。"] : []
  };
}

function renderNextActions(status) {
  // Legacy function placeholder (Actions are now rendered dynamically inside renderRightPanel)
}

function renderWarnings(status) {
  // Legacy function placeholder (Warnings are now rendered dynamically inside renderRightPanel)
}

function renderPageGuards(pageId, status) {
  const guards = {
    dataset: [],
    labelme: [],
    split: [],
    augmentation: [],
    training: [],
    evaluation: [],
    "auto-labeling": [],
    export: []
  };

  if (!status.hasProject) {
    const guard = statusGuard("warning", "尚未載入專案", ["此頁可瀏覽，但操作已停用。"], "前往 Projects 建立或開啟專案。");
    Object.keys(guards).forEach((key) => guards[key].push(guard));
  }
  if (status.hasProject && !status.hasDataset) {
    guards.labelme.push(statusGuard("warning", "尚未匯入資料集", ["Images folder 目前沒有圖片。"], "前往 Dataset 匯入圖片或影片抽幀。"));
    guards.split.push(statusGuard("warning", "尚未匯入資料集", ["不能建立 Train / Val / Test。"], "先完成 Dataset 匯入。"));
    guards.training.push(statusGuard("danger", "目前無法開始訓練", ["尚未匯入資料集。"], "前往 Dataset 匯入圖片。"));
  }
  if (status.hasDataset && !status.labelme.synced) {
    guards.training.push(statusGuard("danger", "目前無法開始訓練", ["尚未同步 LabelMe 標註。"], "前往 LabelMe 頁同步 JSON，再轉換為訓練格式。"));
    guards.split.push(statusGuard("info", "LabelMe 尚未同步", ["此階段仍可設定 split UI，但正式訓練應等待 LabelMe JSON 轉換完成。"], "前往 LabelMe 頁同步 JSON 與執行轉換。"));
  }
  if (status.hasDataset && !status.splitComplete) {
    guards.training.push(statusGuard("danger", "目前無法開始訓練", ["尚未建立 Train / Val / Test。"], "前往 Split 建立資料分散。"));
    guards.augmentation.push(statusGuard("warning", "尚未完成 split", ["套用 augmentation 前需要知道 target split。"], "前往 Split 建立 Train / Val / Test。"));
  }
  if (!status.bestModelExists) {
    guards.evaluation.push(statusGuard("warning", "目前沒有可評估模型", ["尚未完成訓練或尚未產生 best model。"], "完成訓練後再查看 mAP / IoU。"));
    guards.export.push(statusGuard("warning", "目前沒有可匯出模型", ["尚未找到最佳模型權重。"], "完成訓練後再匯出 PT / ONNX。"));
  }

  const activeGuards = guards[pageId] || [];
  const container = qs("#page-guards-container");
  const section = qs("#section-page-guards");
  
  if (container && section) {
    if (activeGuards.length > 0) {
      section.style.display = "block";
      setHTML("#page-guards-container", activeGuards.join(""));
      const pageTitleMap = {
        dataset: "Dataset Page Status",
        labelme: "LabelMe Page Status",
        split: "Split Page Status",
        augmentation: "Augmentation Status",
        training: "Training Status",
        evaluation: "Evaluation Status",
        export: "Export Status"
      };
      setText("#page-guards-title", pageTitleMap[pageId] || "Page Status");
    } else {
      section.style.display = "none";
      setHTML("#page-guards-container", "");
    }
  }
}

function statusGuard(type, title, items, nextAction) {
  return `
    <div class="status-guard ${type}">
      <div class="guard-title">${escapeHtml(title)}</div>
      <ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      <div class="guard-next-actions">${escapeHtml(nextAction)}</div>
    </div>
  `;
}

function updateActionAvailability(status) {
  const rules = {
    project: status.hasProject,
    dataset: status.hasDataset,
    split: status.splitComplete,
    "train-ready": status.trainReady
  };
  qsa(".guarded").forEach((el) => {
    const requirement = el.dataset.requires;
    if (!requirement) return;
    el.disabled = !rules[requirement];
    el.classList.toggle("btn-disabled", !rules[requirement]);
  });
  const startBtn = qs("#btn-start-train");
  if (startBtn) {
    startBtn.disabled = !status.trainReady;
    startBtn.classList.toggle("btn-disabled", !status.trainReady);
  }
}

// Toast 與 Modal 控制
function showToast(message) {
  const toast = qs("#toast");
  if (!toast) return;
  toast.textContent = message;
  toast.hidden = false;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toast.hidden = true;
  }, 3200);
}

function openHistoryModal() {
  const modal = qs("#project-history-modal");
  eventBus.emit("render-recent-projects-list", appState.projects);
  if (modal) modal.hidden = false;
}

function closeHistoryModal() {
  const modal = qs("#project-history-modal");
  if (modal) modal.hidden = true;
}

