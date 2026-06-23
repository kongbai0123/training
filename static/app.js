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
import { initExport, renderExportPage } from "./pages/export.js";
import { initSettings, renderSettingsPage } from "./pages/settings.js";

document.addEventListener("DOMContentLoaded", async () => {
  initPreferences();
  bindGlobalNavigation();
  bindInfoTooltips();
  
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
  initExport();
  initSettings();

  // 載入專案並預設跳轉到 Dashboard
  await loadProjects({ autoOpenLatest: true });
  navigate("dashboard");
});

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
  renderProjectSummary(status);
  renderNextActions(status);
  renderWarnings(status);
  renderPageGuards(appState.currentPage, status);
  renderDatasetPage(status);
  renderLabelMeManager(status);
  renderSplitPage(status);
  renderAugmentationPage(status);
  renderTrainingMonitor();
  renderEvaluationPage(status);
  renderInferencePage(status);
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
  const models = appState.inferenceModels || [];
  const latestRun = models[0]?.run_id || "--";
  const bestCount = models.filter((model) => model.weight_type === "best").length;
  const lastCount = models.filter((model) => model.weight_type === "last").length;
  setHTML("#project-summary", `
    <div class="path-list">
      <div class="path-row"><span>Name</span><code>${escapeHtml(status.projectName)}</code></div>
      <div class="path-row"><span>Task</span><code>${escapeHtml(status.taskType)}</code></div>
      <div class="path-row"><span>Images</span><code>${status.imageCount}</code></div>
      <div class="path-row"><span>Annotated</span><code>${status.annotatedCount}/${status.imageCount}</code></div>
      <div class="path-row"><span>LabelMe</span><code>Backend Connected</code></div>
      <div class="path-row"><span>Split</span><code>${status.splitComplete ? "Ready" : "Not ready"}</code></div>
      <div class="path-row"><span>Training</span><code>${escapeHtml(status.trainingLabel)}</code></div>
      <div class="path-row"><span>Models</span><code>${models.length}</code></div>
      <div class="path-row"><span>Latest run</span><code>${escapeHtml(latestRun)}</code></div>
      <div class="path-row"><span>best.pt</span><code>${bestCount}</code></div>
      <div class="path-row"><span>last.pt</span><code>${lastCount}</code></div>
    </div>
  `);
}

function renderNextActions(status) {
  const actions = [];
  const modelCount = (appState.inferenceModels || []).length;
  if (!status.hasProject) actions.push("前往 Projects 建立或載入專案。");
  if (status.hasProject && !status.hasDataset) actions.push("前往 Dataset 匯入圖片或影片抽幀。");
  if (status.hasDataset && !status.labelme.synced) actions.push("前往 LabelMe 同步 JSON，再轉換為訓練格式。");
  if (status.hasDataset && !status.splitComplete) actions.push("前往 Split 建立 Train / Val / Test。");
  if (status.trainReady) actions.push("前往 Training 啟動或檢查訓練。");
  if (modelCount > 0) actions.push("前往模型測試選擇 best.pt 並測試單張圖片。");
  if (status.trainingLabel === "completed" && modelCount === 0) actions.push("前往 Training 確認 run 是否已產生 best.pt / last.pt。");
  if (actions.length === 0) actions.push("目前沒有建議動作。");
  setHTML("#next-actions-list", actions.map((action) => `<li>${escapeHtml(action)}</li>`).join(""));
}

function renderWarnings(status) {
  const warnings = [];
  const models = appState.inferenceModels || [];
  if (!status.labelme.backendReady) warnings.push("LabelMe backend sync 尚未就緒。");
  if (!status.trainReady) warnings.push("Start Training 會依狀態 disabled。");
  if (!status.hasProject) warnings.push("尚未載入專案，功能頁只會顯示狀態與操作提醒。");
  if (status.hasProject && models.length === 0) warnings.push("No trained weights found for Inference Lab.");
  const selectedModel = models[0];
  if (selectedModel && String(status.taskType || "").includes("segmentation") && !String(selectedModel.task_type || "").includes("segmentation")) {
    warnings.push("Selected model task does not match project task.");
  }
  setHTML("#warning-list", warnings.map((item) => `<div class="activity-item">${escapeHtml(item)}</div>`).join(""));
}

function renderPageGuards(pageId, status) {
  const guards = {
    dataset: [],
    labelme: [],
    split: [],
    augmentation: [],
    training: [],
    evaluation: [],
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
  // 透過 Projects.js 提供的清單產生方法渲染 Modal 內列表
  eventBus.emit("render-recent-projects-list", appState.projects);
  if (modal) modal.hidden = false;
}

function closeHistoryModal() {
  const modal = qs("#project-history-modal");
  if (modal) modal.hidden = true;
}
