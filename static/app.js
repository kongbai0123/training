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
import { initTraining, renderTrainingMonitor } from "./pages/training.js";
import { initEvaluation, renderEvaluationPage } from "./pages/evaluation.js";
import { initExport, renderExportPage } from "./pages/export.js";
import { initSettings, renderSettingsPage } from "./pages/settings.js";

document.addEventListener("DOMContentLoaded", async () => {
  initPreferences();
  bindGlobalNavigation();
  
  // 初始化所有頁面
  initDashboard();
  initProjects();
  initDataset();
  initLabelMe();
  initSplit();
  initAugmentation();
  initTraining();
  initEvaluation();
  initExport();
  initSettings();

  // 載入專案並預設跳轉到 Dashboard
  await loadProjects({ autoOpenLatest: true });
  navigate("dashboard");
});

// 全域導覽與事件訂閱
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
      <div class="path-row"><span>LabelMe</span><code>Backend Connected</code></div>
      <div class="path-row"><span>Split</span><code>${status.splitComplete ? "Ready" : "Not ready"}</code></div>
      <div class="path-row"><span>Training</span><code>${escapeHtml(status.trainingLabel)}</code></div>
    </div>
  `);
}

function renderNextActions(status) {
  const actions = [];
  if (!status.hasProject) actions.push("前往 Projects 建立或開啟專案。");
  if (status.hasProject && !status.hasDataset) actions.push("前往 Dataset 匯入圖片或影片抽幀。");
  if (status.hasDataset && !status.labelme.synced) actions.push("前往 LabelMe 同步 JSON，確認標註進度。");
  if (status.hasDataset && !status.splitComplete) actions.push("前往 Split 建立 Train / Val / Test。");
  if (status.trainReady) actions.push("前往 Training 啟動訓練。");
  if (actions.length === 0) actions.push("目前沒有必要動作。");
  setHTML("#next-actions-list", actions.map((action) => `<li>${escapeHtml(action)}</li>`).join(""));
}

function renderWarnings(status) {
  const warnings = [];
  if (!status.labelme.backendReady) warnings.push("LabelMe backend sync 尚未連線。");
  if (!status.trainReady) warnings.push("Start Training 已依狀態 disabled。");
  if (!status.hasProject) warnings.push("尚未載入專案時，頁面可瀏覽但操作會被停用。");
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
