// Vision Training Studio - Phase 1 Front-end Entry Module
import { eventBus } from "./event_bus.js";
import { 
  appState, 
  initPreferences, 
  applyLanguage, 
  updateLabelMeState, 
  getProjectStatus,
  t
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
import { initAugmentation, renderAugmentationPage } from "./pages/augmentation.js?v=20260625-augmentation-p0";
import { initTraining, renderTrainingMonitor, loadRecommendedConfig } from "./pages/training.js";
import { renderTrainingModeSidebar, renderTrainingWorkspace } from "./pages/training_modes.js";
import { initEvaluation, renderEvaluationPage } from "./pages/evaluation.js";
import { initInference, renderInferencePage } from "./pages/inference.js";
import { initAutoLabeling, renderAutoLabelingPage } from "./pages/auto_labeling.js?v=20260624-auto-label-readable";
import { initExport, renderExportPage } from "./pages/export.js";
import { initSettings, renderSettingsPage } from "./pages/settings.js";

document.addEventListener("DOMContentLoaded", async () => {
  initPreferences();
  await bootstrapSession();
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

async function bootstrapSession() {
  try {
    const payload = await apiFetch("/api/bootstrap");
    appState.bootstrap = {
      token: payload?.token || "",
      startedAt: payload?.started_at || "",
      expiresAt: payload?.expires_at || "",
      version: payload?.version || "",
      environment: payload?.environment || "",
    };
    window.__VTS_BOOTSTRAP = appState.bootstrap;
    if (appState.bootstrap.token) {
      localStorage.setItem("vts-session-token", appState.bootstrap.token);
    }
  } catch (err) {
    console.warn("Unable to fetch bootstrap token:", err.message);
    appState.bootstrap.token = "";
  }
}

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
    btn.addEventListener("click", () => {
      if (btn.dataset.page === "projects") {
        eventBus.emit("open-create-project-modal");
        return;
      }
      navigate(btn.dataset.page);
    });
  });
  
  document.addEventListener("click", (event) => {
    const navTarget = event.target.closest("[data-nav]");
    if (!navTarget) return;
    event.preventDefault();
    if (navTarget.dataset.nav === "projects") {
      eventBus.emit("open-create-project-modal");
      return;
    }
    navigate(navTarget.dataset.nav);
  });

  // History Modal 觸發與關閉
  qs("#btn-header-save-project")?.addEventListener("click", saveCurrentProject);
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
  
  renderHeaderStatus();

  // 觸發各子頁面渲染
  renderDashboard(status);
  renderRightPanel(appState.currentPage, status);
  renderPageGuards(appState.currentPage, status);
  renderDatasetPage(status);
  renderLabelMeManager(status);
  renderSplitPage(status);
  renderAugmentationPage(status);
  renderTrainingMonitor();
  renderTrainingModeSidebar();
  renderTrainingWorkspace();
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

async function saveCurrentProject() {
  const projectId = appState.currentProjectId;
  if (!projectId) {
    showToast(t("headerSaveNoProject"));
    return;
  }

  const btn = qs("#btn-header-save-project");
  const originalHtml = btn?.innerHTML;
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i><span>${escapeHtml(t("headerSave"))}</span>`;
  }

  try {
    appState.currentProject = await requestProjectSave(projectId);
    appState.currentProjectId = projectId;
    appState.currentProjectClasses = [...(appState.currentProject?.class_names || [])];
    setText("#current-project-title", appState.currentProject.project_name || projectId);
    updateLabelMeState();
    await checkCurrentTrainStatus();
    renderAll();
    showToast(t("headerSaveDone"));
  } catch (err) {
    showToast(t("headerSaveFailed", { message: err.message }));
  } finally {
    if (btn) {
      btn.disabled = !appState.currentProjectId;
      btn.innerHTML = originalHtml || `<i class="fa-solid fa-floppy-disk"></i><span data-i18n="headerSave">${escapeHtml(t("headerSave"))}</span>`;
      applyLanguage(appState.settings.language);
    }
  }
}

async function requestProjectSave(projectId) {
  const headers = {};
  if (appState.bootstrap?.token) {
    headers["X-VTS-Token"] = appState.bootstrap.token;
  }

  const res = await fetch(`/api/projects/${projectId}/save`, {
    method: "POST",
    headers,
  });
  if (res.ok) return res.json();
  if (res.status === 404 || res.status === 405) {
    return apiFetch(`/api/projects/${projectId}`);
  }

  let detail = "";
  try {
    const data = await res.json();
    detail = data.detail || JSON.stringify(data);
  } catch {
    detail = await res.text();
  }
  throw new Error(detail || `HTTP ${res.status}`);
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

function renderHeaderStatus() {
  const health = appState.systemHealth || {};
  const device = health.device || {};
  const memory = health.memory || {};
  const hasGpu = device.has_gpu === true;
  const isHealthy = health.status === "healthy";

  setText("#header-gpu-value", hasGpu ? (device.device_name || "GPU ready") : "CPU mode");
  if (memory.status === "available" && memory.available_gb !== null && memory.available_gb !== undefined) {
    setText("#header-ram-value", `${memory.available_gb} GB free`);
  } else {
    setText("#header-ram-value", "Unavailable");
  }
  setText("#header-health-label", isHealthy ? "Healthy" : "Offline");

  const dot = qs("#api-status-dot");
  if (dot) {
    dot.classList.toggle("online", isHealthy);
    dot.classList.toggle("offline", !isHealthy);
  }

  const saveBtn = qs("#btn-header-save-project");
  if (saveBtn) {
    saveBtn.disabled = !appState.currentProjectId;
    saveBtn.classList.toggle("btn-disabled", !appState.currentProjectId);
  }
}

// UI 面板渲染
function renderProjectSummary(status, pageId = appState.currentPage) {
  const taskLabel = String(status.taskType || "--")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
  const titleEl = qs("#project-context-title");
  if (titleEl) titleEl.textContent = pageId === "dashboard" ? "Current Project" : "Project Context";

  if (!status.hasProject) {
    setHTML("#project-summary", `
      <div class="summary-empty compact">
        <p>No project opened.</p>
      </div>
    `);
    return;
  }

  if (pageId === "dashboard") {
    setHTML("#project-summary", `
      <div class="path-list project-context-full">
        <div class="path-row"><span>Name</span><code>${escapeHtml(status.projectName)}</code></div>
        <div class="path-row"><span>Task</span><code>${escapeHtml(taskLabel)}</code></div>
        <div class="path-row"><span>Images</span><code>${status.imageCount}</code></div>
        <div class="path-row"><span>Annotated</span><code>${status.annotatedCount}/${status.imageCount}</code></div>
        <div class="path-row"><span>Split</span><code>${status.splitComplete ? "Ready" : "Not ready"}</code></div>
      </div>
    `);
    return;
  }

  setHTML("#project-summary", `
    <div class="project-context-compact">
      <div>
        <strong>${escapeHtml(status.projectName)}</strong>
        <span>${escapeHtml(taskLabel)}</span>
      </div>
      <span class="summary-badge badge-${status.hasDataset ? "success" : "neutral"}">${status.hasDataset ? `${status.imageCount} images` : "No images"}</span>
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
  renderProjectSummary(status, pageId);

  const builder = RIGHT_PANEL_CONFIG[pageId];
  const container = qs("#page-context-container");
  const section = qs("#section-page-context");
  const titleEl = qs("#page-context-title");

  if (!container || !section) return;

  const bypassEmptyPages = ["dashboard", "projects", "settings"];
  const showEmpty = !status.hasProject && !bypassEmptyPages.includes(pageId);

  if (showEmpty) {
    section.style.display = "block";
    if (titleEl) titleEl.textContent = getPageTitle(pageId);
    container.innerHTML = `
      <div class="summary-empty">
        <p>Please create or open a project first.</p>
        <button class="btn btn-secondary btn-sm" data-nav="projects">Go to Projects</button>
      </div>
    `;
    setHTML("#next-actions-list", `<li>Open Projects or Browse History to choose a project.</li>`);
    setHTML("#warning-list", `<div class="summary-warning-item">No project is open for this page.</div>`);
    return;
  }

  if (!builder) {
    section.style.display = "none";
    container.innerHTML = "";
    setHTML("#next-actions-list", "<li>No suggested action for this page.</li>");
    setHTML("#warning-list", "");
    return;
  }

  const config = builder(status);
  if (titleEl && config.title) titleEl.textContent = config.title;

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
    container.innerHTML = rowsHtml
      ? `<div class="path-list" style="gap: 0;">${rowsHtml}</div>`
      : `<div class="summary-empty"><p>No page status available.</p></div>`;
  }

  const actions = config.actions || [];
  setHTML("#next-actions-list", actions.length > 0
    ? actions.map(act => `<li>${escapeHtml(act)}</li>`).join("")
    : "<li>No suggested action right now.</li>");

  const warnings = config.warnings || [];
  const notes = config.notes || [];
  const warningTitle = qs("#warning-list")?.closest(".summary-section")?.querySelector("h2");
  if (warningTitle) warningTitle.textContent = warnings.length > 0 ? "Warnings" : (notes.length > 0 ? "Notes" : "Warnings");
  setHTML("#warning-list", warnings.length > 0
    ? warnings.map(warn => `<div class="summary-warning-item">${escapeHtml(warn)}</div>`).join("") + notes.map(note => `<div class="summary-info-item">${escapeHtml(note)}</div>`).join("")
    : notes.map(note => `<div class="summary-info-item">${escapeHtml(note)}</div>`).join("")
  );
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
    ? Math.round((status.annotatedCount / Math.max(status.imageCount, 1)) * 50 + (status.splitComplete ? 30 : 0) + (status.bestModelExists ? 20 : 0))
    : 0;

  const rows = status.hasProject ? [
    { label: "Health Score", value: `${healthScore}%`, badgeType: healthScore > 75 ? "success" : (healthScore > 40 ? "warning" : "danger") },
    { label: "Images", value: String(status.imageCount) },
    { label: "Annotated", value: `${status.annotatedCount}/${status.imageCount}` },
    { label: "Split", value: status.splitComplete ? "Ready" : "Not ready", badgeType: status.splitComplete ? "success" : "danger" },
    { label: "Best Model", value: status.bestModelExists ? "Exists" : "None", badgeType: status.bestModelExists ? "success" : "neutral" }
  ] : [];

  const actions = [];
  if (!status.hasProject) actions.push("Create a new project or open one from Browse History.");
  else if (!status.hasDataset) actions.push("Import images or extracted video frames in Dataset.");
  else if (!status.labelme.synced) actions.push("Sync LabelMe JSON and review annotation issues.");
  else if (!status.splitComplete) actions.push("Create Train / Val / Test split.");
  else actions.push("Open Training and start a configured run.");

  const warnings = [];
  if (!status.hasProject) warnings.push("No active project. Most workflow actions are waiting for a project.");
  else if (!status.hasDataset) warnings.push("The active project has no imported images.");

  return {
    title: "Project Readiness",
    rows,
    actions,
    warnings,
    emptyState: !status.hasProject ? {
      message: "Create or open a project to see dashboard readiness.",
      actionLabel: "Browse History",
      actionNav: "history"
    } : null
  };
}

function buildProjectsRightPanel(status) {
  return {
    title: "Projects Status",
    rows: [
      { label: "Total Projects", value: String(appState.projects?.length || 0) },
      { label: "Active Project", value: status.hasProject ? status.projectName : "None", isCode: true }
    ],
    actions: ["Use New Project to create a project.", "Use Browse History to open an existing project."],
    warnings: appState.projects?.length === 0 ? ["No projects are available yet."] : []
  };
}

function buildDatasetRightPanel(status) {
  const images = appState.currentProject?.images || [];
  const videos = new Set(images.map(img => img.source_video).filter(Boolean));
  const duplicates = images.filter(img => img.quality?.is_duplicate).length;
  const invalid = images.filter(img => img.quality?.is_corrupted).length;
  const score = status.hasDataset ? Math.max(0, 100 - (duplicates * 5) - (invalid * 10)) : 0;

  const warnings = [];
  if (!status.hasDataset) warnings.push("No images imported. Dataset-dependent actions are disabled.");
  if (duplicates > 0) warnings.push(`${duplicates} possible duplicate images detected.`);
  if (invalid > 0) warnings.push(`${invalid} corrupted or invalid files detected.`);

  return {
    title: "Dataset Status",
    rows: [
      { label: "Images", value: String(status.imageCount) },
      { label: "Videos", value: String(videos.size) },
      { label: "Quality", value: status.hasDataset ? `${score}/100` : "Not run", badgeType: score > 80 ? "success" : (score > 50 ? "warning" : "neutral") },
      { label: "Duplicates", value: String(duplicates), badgeType: duplicates > 0 ? "warning" : null },
      { label: "Invalid", value: String(invalid), badgeType: invalid > 0 ? "danger" : null }
    ],
    actions: ["Import images or a folder.", "Run quality check before labeling.", "Open LabelMe after images are ready."],
    warnings
  };
}

function buildLabelMeRightPanel(status) {
  const lm = appState.labelme || {};
  const warnings = [];
  if (!status.hasDataset) warnings.push("No images found. Import images in Dataset first.");
  if ((lm.missingJson || 0) > 0) warnings.push(`${lm.missingJson} images are missing LabelMe JSON.`);
  if ((lm.invalidJson || 0) > 0) warnings.push(`${lm.invalidJson} invalid JSON files need review.`);
  if ((lm.unknownLabels || 0) > 0) warnings.push(`${lm.unknownLabels} unknown labels are not in the project class list.`);

  return {
    title: "LabelMe Status",
    rows: [
      { label: "Images", value: String(status.imageCount) },
      { label: "JSON", value: String(lm.jsonCount || 0) },
      { label: "Missing", value: String(lm.missingJson || 0), badgeType: lm.missingJson > 0 ? "warning" : null },
      { label: "Invalid", value: String(lm.invalidJson || 0), badgeType: lm.invalidJson > 0 ? "danger" : null },
      { label: "Completion", value: `${status.labelme.completionRate || 0}%`, badgeType: (status.labelme.completionRate || 0) >= 95 ? "success" : "neutral" }
    ],
    actions: ["Open LabelMe with the project image folder.", "Rescan annotation status after editing.", "Review invalid or unknown labels before Split."],
    warnings
  };
}

function buildSplitRightPanel(status) {
  const warnings = [];
  if (!status.splitComplete) warnings.push("Train / Val / Test split is not ready. Training cannot start safely.");
  if ((status.splitCounts.val || 0) === 0 && status.splitComplete) warnings.push("Validation set count is 0. Recreate the split with validation data.");

  return {
    title: "Split Status",
    rows: [
      { label: "Train", value: String(status.splitCounts.train || 0) },
      { label: "Val", value: String(status.splitCounts.val || 0) },
      { label: "Test", value: String(status.splitCounts.test || 0) },
      { label: "Quality", value: `${status.splitQuality || 0}/100`, badgeType: status.splitQuality > 80 ? "success" : "neutral" },
      { label: "Leakage Risk", value: status.splitComplete ? "Low" : "Unknown", badgeType: status.splitComplete ? "success" : "warning" }
    ],
    actions: ["Create class-balanced split.", "Review class balance before training.", "Configure augmentation after split is ready."],
    warnings
  };
}

function buildAugmentationRightPanel(status) {
  const multiplier = parseInt(qs("#aug-multiplier")?.value || qs("#multiplier")?.value || "1", 10);
  const trainCount = status.splitCounts.train || 0;
  const valCount = status.splitCounts.val || 0;
  const testCount = status.splitCounts.test || 0;
  const valTestCount = valCount + testCount;
  const readinessState = qs("#aug-readiness-card")?.dataset?.state || "blocked_no_project";
  const previewReady = readinessState === "preview_ready";
  const previewStale = readinessState === "preview_stale";
  const hasPreviewImage = Boolean(qs("#aug-preview-select-img")?.value);
  const generatedCopies = trainCount * multiplier;

  let statusLabel = "Blocked";
  let riskLabel = "Blocked";
  if (status.hasProject && status.hasDataset && status.splitComplete && trainCount > 0) {
    statusLabel = previewReady ? "Preview ready" : "Ready";
    riskLabel = previewReady ? "Low" : (previewStale ? "Preview stale" : "Preview required");
  }

  const actions = [];
  const warnings = [];
  const notes = ["Val/Test 維持排除，避免評估資料洩漏。"];
  if (!status.hasProject) {
    actions.push("建立或開啟專案。");
    warnings.push("尚未開啟專案。");
  } else if (!status.hasDataset) {
    actions.push("前往 Dataset 匯入圖片。");
    actions.push("同步標註。");
    actions.push("建立 Train / Val / Test split。");
    warnings.push("尚未匯入圖片，無法進行擴充。");
  } else if (!status.splitComplete || trainCount === 0) {
    actions.push("建立 Train / Val / Test split。");
    warnings.push("套用 Train-only augmentation 前必須先建立 split。");
  } else if (!hasPreviewImage) {
    actions.push("確認 Train split 中有可預覽圖片。");
    warnings.push("目前沒有可預覽圖片。");
  } else if (previewStale) {
    actions.push("重新產生 Preview。");
    actions.push("檢查 Risk Check。");
    warnings.push("設定已變更，Preview 需要重新產生。");
  } else if (!previewReady) {
    actions.push("選擇 preset 或自訂策略。");
    actions.push("產生 Preview。");
    actions.push("檢查 Risk Check。");
  } else {
    actions.push("檢查預覽結果。");
    actions.push("套用到 Train Split。");
    actions.push("進行模型訓練。");
  }

  return {
    title: "Augmentation Status",
    rows: [
      { label: "Status", value: statusLabel, badgeType: previewReady ? "success" : (statusLabel === "Ready" ? "warning" : "danger") },
      { label: "Target", value: "Train split", isCode: true },
      { label: "Output", value: `+${generatedCopies}`, isCode: true },
      { label: "Risk", value: riskLabel, badgeType: previewReady ? "success" : "warning" }
    ],
    actions,
    warnings,
    notes
  };
}

function buildTrainingRightPanel(status) {
  const gpu = appState.systemHealth?.device?.device_name || "CPU";
  const model = qs("#train-model")?.value || "--";
  const runs = appState.currentProject?.training_runs || [];
  const latestRun = runs.length > 0 ? runs[runs.length - 1] : null;
  const runStatus = latestRun?.status ?? "--";
  const statusBadge = runStatus === "completed" ? "success" : runStatus === "failed" ? "danger" : runStatus === "training" ? "warning" : "neutral";

  const warnings = [];
  if (!status.hasDataset) warnings.push("Dataset is missing. Import images before training.");
  if (!status.labelme.synced) warnings.push("LabelMe annotations are not synced.");
  if (!status.splitComplete) warnings.push("Train / Val / Test split is missing.");
  if (gpu === "CPU" || gpu.includes("unavailable") || gpu.includes("Backend")) warnings.push("GPU is unavailable or backend health is missing; training may be slow.");

  const actions = [];
  if (!status.hasDataset) actions.push("Go to Dataset and import images.");
  if (status.hasDataset && !status.labelme.synced) actions.push("Go to LabelMe and sync annotations.");
  if (status.hasDataset && status.labelme.synced && !status.splitComplete) actions.push("Create Train / Val / Test split.");
  if (status.trainReady) actions.push("Review settings, then start training.");

  return {
    title: "Training Context",
    rows: [
      { label: "Start status", value: status.trainReady ? "Ready" : "Blocked", badgeType: status.trainReady ? "success" : "danger" },
      { label: "Dataset", value: status.hasDataset ? `${status.imageCount} images` : "Missing", badgeType: status.hasDataset ? "success" : "danger" },
      { label: "Labels", value: status.labelme.synced ? `${status.annotatedCount}/${status.imageCount}` : "Not synced", badgeType: status.labelme.synced ? "success" : "danger" },
      { label: "Split", value: status.splitComplete ? `${status.splitCounts.train}/${status.splitCounts.val}/${status.splitCounts.test}` : "Missing", badgeType: status.splitComplete ? "success" : "danger" },
      { label: "Model", value: model },
      { label: "Hardware", value: gpu, isCode: true },
      { label: "Run", value: latestRun?.run_id ?? "--", isCode: true },
      { label: "Run status", value: runStatus, badgeType: statusBadge }
    ],
    actions,
    warnings
  };
}

function buildEvaluationRightPanel(status) {
  const models = appState.models || [];
  const model = models.find(m => m.weight_type === "best") || models[0];
  const formatNum = (v) => (v === null || v === undefined) ? "--" : Number(v).toFixed(3);

  return {
    title: "Evaluation Status",
    rows: [
      { label: "mAP50", value: model ? formatNum(model.best_map50_m) : "--", isCode: true },
      { label: "mAP50-95", value: model ? formatNum(model.best_map50_95_m) : "--", isCode: true },
      { label: "Precision", value: model ? formatNum(model.precision) : "--" },
      { label: "Recall", value: model ? formatNum(model.recall) : "--" },
      { label: "Model", value: model ? model.weight_type : "--", isCode: true },
      { label: "Run", value: model?.run_id ?? "--", isCode: true }
    ],
    actions: ["Run evaluation after a best model exists.", "Review confusion matrix and failure cases."],
    warnings: !status.bestModelExists ? ["No trained best model found yet."] : []
  };
}

function buildInferenceRightPanel(status) {
  const models = appState.models || [];
  const bestCount = models.filter((m) => m.weight_type === "best").length;
  const lastCount = models.filter((m) => m.weight_type === "last").length;
  const latestRun = models.length > 0 ? (models[0]?.run_id ?? "--") : "--";
  const selId = appState.inferenceSelectedModelId;
  const selModel = selId ? models.find((m) => m.model_id === selId) : null;

  const warnings = [];
  if (models.length === 0) warnings.push("No trained weights found. Complete Training first.");

  return {
    title: "Inference Lab Status",
    rows: [
      { label: "Models", value: String(models.length) },
      { label: "best.pt", value: String(bestCount) },
      { label: "last.pt", value: String(lastCount) },
      { label: "Latest Run", value: latestRun, isCode: true },
      { label: "Selected", value: selModel ? `${selModel.weight_type} (${selModel.run_id || "?"})` : "--", isCode: true }
    ],
    actions: ["Select a registered model.", "Upload one test image.", "Run single-image inference."],
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

  const warnings = ["Draft annotations must be reviewed before applying to current labels."];
  if (models.length === 0) warnings.unshift("No model available for auto-labeling. Train or import a model first.");
  if (models.length > 0 && compatibleModels.length === 0) warnings.unshift("Available models do not match the project task type.");

  return {
    title: "Auto-Labeling Status",
    rows: [
      { label: "Models", value: String(models.length) },
      { label: "Compatible", value: String(compatibleModels.length), badgeType: compatibleModels.length > 0 ? "success" : "warning" },
      { label: "Output", value: "Draft only", badgeType: "neutral" },
      { label: "Format", value: "LabelMe / YOLO", isCode: true },
      { label: "Backend", value: "Pending", badgeType: "neutral" }
    ],
    actions: ["Choose input images.", "Select best.pt or last.pt.", "Generate drafts, then review before apply."],
    warnings
  };
}

function buildExportRightPanel(status) {
  const models = appState.models || [];
  const bestModel = models.find((m) => m.weight_type === "best");
  return {
    title: "Export Status",
    rows: [
      { label: "Weights", value: String(models.length) },
      { label: "Best Run", value: bestModel?.run_id ?? "--", isCode: true },
      { label: "ONNX", value: status.bestModelExists ? "Ready" : "Unavailable", badgeType: status.bestModelExists ? "success" : "neutral" },
      { label: "Report", value: "Ready", badgeType: "success" }
    ],
    actions: ["Select a model artifact.", "Export ONNX or report.", "Verify exported package before deployment."],
    warnings: !status.bestModelExists ? ["No best model is available for export."] : []
  };
}

function buildHistoryRightPanel(status) {
  const runs = appState.currentProject?.training_runs?.length || 0;
  const imports = appState.currentProject?.imports_history?.length || 0;
  return {
    title: "History Status",
    rows: [
      { label: "Projects", value: String(appState.projects?.length || 0) },
      { label: "Runs", value: String(runs) },
      { label: "Imports", value: String(imports) }
    ],
    actions: ["Open Browse History for project file details.", "Review recent imports, runs, and exports."],
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
      { label: "Device", value: gpu },
      { label: "LabelMe", value: status.labelme.backendReady ? "Connected" : "Disconnected", badgeType: status.labelme.backendReady ? "success" : "danger" },
      { label: "API", value: isHealthy ? "Healthy" : "Offline", badgeType: isHealthy ? "success" : "danger" }
    ],
    actions: ["Switch language or theme.", "Use diagnostics if the backend is offline."],
    warnings: !isHealthy ? ["API health check failed or backend is unavailable."] : []
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
    guards.training.push(statusGuard("danger", "目前無法開始訓練", ["尚未重新掃描 LabelMe 標註狀態。"], "前往 LabelMe 頁重新掃描標註狀態，再轉換為訓練格式。"));
    guards.split.push(statusGuard("info", "LabelMe 尚未掃描", ["此階段仍可設定 split UI，但正式訓練應等待 LabelMe JSON 轉換完成。"], "前往 LabelMe 頁重新掃描標註狀態與執行轉換。"));
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

async function openHistoryModal() {
  const modal = qs("#project-history-modal");
  await loadProjects({ autoOpenLatest: false });
  eventBus.emit("render-project-history-modal");
  if (modal) modal.hidden = false;
}

function closeHistoryModal() {
  const modal = qs("#project-history-modal");
  if (modal) modal.hidden = true;
}

