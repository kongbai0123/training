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

// 頛??辣
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
  await bootstrapSession();
  bindGlobalNavigation();
  bindInfoTooltips();
  
  // 頛蝖祇?蝟餌絞????憛?頞?頞嚗?  fetchSystemHealth();

  // ????????  initDashboard();
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

  // 頛撠?銝阡?閮剛歲頧 Dashboard
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

// ?典?撠汗??隞嗉???function bindInfoTooltips() {
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

  // History Modal 閫貊????  qs("#btn-header-history")?.addEventListener("click", openHistoryModal);
  qs("#btn-close-history")?.addEventListener("click", closeHistoryModal);
  qs("#project-history-modal")?.addEventListener("click", (event) => {
    if (event.target.id === "project-history-modal") closeHistoryModal();
  });

  // EventBus 鈭辣??
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
    showToast("??歇??渡?");
  });

  eventBus.on("project-deleted", async (projectId) => {
    if (appState.currentProjectId === projectId) {
      appState.currentProjectId = null;
      appState.currentProject = null;
      appState.trainingStatus = null;
      updateLabelMeState();
      setText("#current-project-title", "撠頛撠?");
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
  
  // 閫貊???皜脫?
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

// 頛????獢?async function loadProjects(options = {}) {
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
    showToast(`?⊥?霈??獢??殷?${err.message}`);
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
    // 瑼Ｘ銝阡?閮剛?蝺?WebSocket
    await checkCurrentTrainStatus();
    // 頛閰脣?獢?璅∪?皜
    try {
      const models = await apiFetch(`/api/projects/${projectId}/models`);
      appState.models = Array.isArray(models) ? models : [];
    } catch (e) {
      console.warn("Failed to prefetch models:", e.message);
      appState.models = [];
    }
    // 頛??刻?蔭
    await loadRecommendedConfig();
    renderAll();
    if (!options.stayOnPage) navigate(options.page || "dashboard");
  } catch (err) {
    showToast(`?⊥?頛撠?嚗?{err.message}`);
  }
}

async function checkCurrentTrainStatus() {
  if (!appState.currentProjectId) return;
  try {
    appState.trainingStatus = await apiFetch(`/api/projects/${appState.currentProjectId}/train/status`);
    // 閫貊閮毀 WebSocket ???賣炎??    eventBus.emit("check-training-websocket");
  } catch {
    appState.trainingStatus = null;
  }
}

// UI ?Ｘ皜脫?
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

// 蝯曹??葡????(Separation of Concerns & XSS ?脰風)
function renderRightPanel(pageId, status) {
  // 1. 皜脫?蝎曄陛??獢??閬?  renderProjectSummary(status);

  // 2. ?脣??撠惇??瑽? Context 鞈?
  const builder = RIGHT_PANEL_CONFIG[pageId];
  const container = qs("#page-context-container");
  const section = qs("#section-page-context");
  
  if (!container || !section) return;

  // ?文??臬?函撠????憿舐內 Empty State
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
    
    // 皜脫? Empty State 銝? Suggested Actions ??Warnings
    setHTML("#next-actions-list", `<li>?? <a href="#" data-nav="projects">Projects</a> 撱箇?????獢?/li>`);
    setHTML("#warning-list", `<div class="summary-warning-item">撠頛撠?嚗????獢?/div>`);
    return;
  }

  if (!builder) {
    section.style.display = "none";
    container.innerHTML = "";
    setHTML("#next-actions-list", "<li>?桀?瘝?撱箄降????/li>");
    setHTML("#warning-list", "");
    return;
  }

  // ??閮?敺?蝯?????  const config = builder(status);
  
  // 皜脫? Context 璅?
  const titleEl = qs("#page-context-title");
  if (titleEl && config.title) {
    titleEl.textContent = config.title;
  }

  // 3. 皜脫? Page Context ?批捆 (XSS 摰 escape ??)
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
    container.innerHTML = rowsHtml ? `<div class="path-list" style="gap: 0;">${rowsHtml}</div>` : `<div class="summary-empty"><p>?桀?瘝??舫＊蝷箇??鞈???/p></div>`;
  }

  // 4. ??皜脫? Next Suggested Actions (XSS 摰??)
  const actions = config.actions || [];
  if (actions.length > 0) {
    setHTML("#next-actions-list", actions.map(act => `<li>${escapeHtml(act)}</li>`).join(""));
  } else {
    setHTML("#next-actions-list", "<li>?桀?瘝?撱箄降????/li>");
  }

  // 5. ??皜脫? Warnings (XSS 摰??)
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
  const focus = appState.dashboardFocus || "overview";
  const healthScore = calculateProjectHealth(status);
  const baseRows = [
    { label: "Project health", value: `${healthScore}%`, badgeType: healthScore >= 80 ? "success" : healthScore >= 45 ? "warning" : "danger" },
    { label: "Dataset", value: status.hasDataset ? `${status.imageCount} images` : "No images", badgeType: status.hasDataset ? "success" : "warning" },
    { label: "Annotation", value: status.imageCount > 0 ? `${status.annotatedCount}/${status.imageCount}` : "Unavailable" },
    { label: "Split", value: status.splitComplete ? "Ready" : "Not ready", badgeType: status.splitComplete ? "success" : "warning" },
    { label: "Model", value: status.bestModelExists ? "Available" : "Not trained", badgeType: status.bestModelExists ? "success" : "neutral" }
  ];

  const contexts = {
    overview: {
      title: "Dashboard Context",
      rows: baseRows,
      actions: buildDashboardActions(status),
      warnings: buildDashboardWarnings(status)
    },
    dataset: {
      title: "Dataset Context",
      rows: [
        { label: "Images", value: String(status.imageCount) },
        { label: "Dataset status", value: status.hasDataset ? "Imported" : "Empty", badgeType: status.hasDataset ? "success" : "warning" },
        { label: "Next gate", value: "Annotation" }
      ],
      actions: status.hasDataset ? ["Run quality check", "Open Annotation Manager"] : ["Import images or a dataset folder"],
      warnings: status.hasDataset ? [] : ["Training cannot start until images are imported."]
    },
    labelme: {
      title: "Annotation Context",
      rows: [
        { label: "Annotated", value: `${status.annotatedCount}/${status.imageCount}` },
        { label: "Missing", value: String(status.unannotatedCount), badgeType: status.unannotatedCount > 0 ? "warning" : "success" },
        { label: "LabelMe JSON", value: String(status.labelme.jsonCount || 0) }
      ],
      actions: status.labelme.synced ? ["Review annotation quality", "Continue to Split"] : ["Sync LabelMe JSON", "Review missing annotations"],
      warnings: status.unannotatedCount > 0 ? [`${status.unannotatedCount} images still need annotation review.`] : []
    },
    "auto-labeling": {
      title: "Auto-Labeling Context",
      rows: [
        { label: "Unlabeled images", value: String(status.unannotatedCount) },
        { label: "Available models", value: String((appState.models || []).length) },
        { label: "Target", value: "Draft annotations", isCode: true }
      ],
      actions: status.bestModelExists ? ["Create draft annotations", "Review drafts before applying"] : ["Train or import a model first"],
      warnings: status.bestModelExists ? ["Drafts should be reviewed before updating current annotations."] : ["No trained weights are available for auto-labeling."]
    },
    split: {
      title: "Split Context",
      rows: [
        { label: "Train", value: String(status.splitCounts.train) },
        { label: "Val", value: String(status.splitCounts.val) },
        { label: "Test", value: String(status.splitCounts.test) },
        { label: "Ready", value: status.splitComplete ? "Yes" : "No", badgeType: status.splitComplete ? "success" : "warning" }
      ],
      actions: status.splitComplete ? ["Review split balance", "Continue to Training"] : ["Create Train / Val / Test split"],
      warnings: status.splitComplete ? [] : ["Training is blocked until a split exists."]
    },
    augmentation: {
      title: "Augmentation Context",
      rows: [
        { label: "Scope", value: "Train only", isCode: true },
        { label: "Split ready", value: status.splitComplete ? "Yes" : "No", badgeType: status.splitComplete ? "success" : "warning" },
        { label: "Configured", value: appState.currentProject?.augmentation_config ? "Yes" : "No" }
      ],
      actions: ["Choose preset or custom checks", "Preview before applying"],
      warnings: status.splitComplete ? ["Do not apply augmentation to validation or test sets."] : ["Create a split before applying augmentation."]
    },
    training: {
      title: "Training Context",
      rows: [
        { label: "Dataset ready", value: status.hasDataset ? "Yes" : "No", badgeType: status.hasDataset ? "success" : "danger" },
        { label: "Annotation ready", value: status.labelme.synced ? "Yes" : "No", badgeType: status.labelme.synced ? "success" : "danger" },
        { label: "Split ready", value: status.splitComplete ? "Yes" : "No", badgeType: status.splitComplete ? "success" : "danger" },
        { label: "Training", value: status.trainReady ? "Ready" : "Blocked", badgeType: status.trainReady ? "success" : "danger" }
      ],
      actions: status.trainReady ? ["Start training", "Review recommended model settings"] : ["Resolve blockers before starting training"],
      warnings: status.blockers.length > 0 ? status.blockers : []
    },
    evaluation: {
      title: "Evaluation Context",
      rows: [
        { label: "Model", value: status.bestModelExists ? "Available" : "Missing", badgeType: status.bestModelExists ? "success" : "warning" },
        { label: "Metrics", value: status.bestModelExists ? "Ready to review" : "Unavailable" }
      ],
      actions: status.bestModelExists ? ["Open Evaluation", "Review failure cases"] : ["Complete a training run first"],
      warnings: status.bestModelExists ? [] : ["No model has been trained yet."]
    },
    inference: {
      title: "Inference Lab Context",
      rows: [
        { label: "Weights", value: String((appState.models || []).length) },
        { label: "Input", value: "Single image", isCode: true },
        { label: "Output", value: "Inference job", isCode: true }
      ],
      actions: (appState.models || []).length > 0 ? ["Select a model", "Upload a test image"] : ["Train a model first"],
      warnings: (appState.models || []).length > 0 ? [] : ["No best.pt or last.pt was found."]
    },
    export: {
      title: "Export Context",
      rows: [
        { label: "Model", value: status.bestModelExists ? "Available" : "Missing", badgeType: status.bestModelExists ? "success" : "warning" },
        { label: "ONNX", value: status.bestModelExists ? "Ready" : "Unavailable" }
      ],
      actions: status.bestModelExists ? ["Export model package", "Generate report"] : ["Train a model before exporting"],
      warnings: status.bestModelExists ? [] : ["Export is unavailable without trained weights."]
    }
  };

  return contexts[focus] || contexts.overview;
}

function buildDashboardActions(status) {
  if (!status.hasProject) return ["Create or open a project."];
  if (!status.hasDataset) return ["Import images in Dataset Manager."];
  if (!status.labelme.synced) return ["Sync LabelMe annotations."];
  if (!status.splitComplete) return ["Create Train / Val / Test split."];
  if (!status.bestModelExists) return ["Start training or review training settings."];
  return ["Open Inference Lab or Export the trained model."];
}

function buildDashboardWarnings(status) {
  const warnings = [];
  if (!status.hasProject) warnings.push("No project is currently open.");
  if (status.hasProject && !status.hasDataset) warnings.push("Dataset is empty.");
  if (status.hasDataset && status.unannotatedCount > 0) warnings.push(`${status.unannotatedCount} images need annotation review.`);
  if (status.hasDataset && !status.splitComplete) warnings.push("Training is blocked until Train / Val / Test is created.");
  return warnings;
}

function calculateProjectHealth(status) {
  let score = 0;
  if (status.hasProject) score += 10;
  if (status.hasDataset) score += 20;
  if (status.annotationRate >= 95) score += 25;
  else if (status.annotationRate > 0) score += Math.round(status.annotationRate * 0.2);
  if (status.splitComplete) score += 20;
  if (status.bestModelExists) score += 15;
  if (appState.currentProject?.current?.export_id) score += 10;
  return Math.min(100, score);
}


function buildProjectsRightPanel(status) {
  return {
    title: "Projects Status",
    rows: [
      { label: "Total Projects", value: String(appState.projects?.length || 0) }
    ],
    actions: ["?典椰?寡”?桐葉憛怠?迂???伐?撱箇??啣?獢?, "敺風蝔??”銝剖?頛??獢?],
    warnings: appState.projects?.length === 0 ? ["蝟餌絞?桀?瘝?隞颱?撠???] : []
  };
}

function buildDatasetRightPanel(status) {
  const images = appState.currentProject?.images || [];
  const videos = new Set(images.map(img => img.source_video).filter(Boolean));
  const duplicates = images.filter(img => img.quality?.is_duplicate).length;
  const invalid = images.filter(img => img.quality?.is_corrupted).length;
  const score = status.hasDataset ? Math.max(0, 100 - (duplicates * 5) - (invalid * 10)) : 0;

  const actions = ["Run quality check ?瑁??釭瑼Ｘ葫", "Go to LabelMe ?脰?璅?蝞∠?"];
  const warnings = [];
  if (duplicates > 0) warnings.push(`?菜葫??${duplicates} 撘菟???????嚗遣霅唳??);
  if (invalid > 0) warnings.push(`?菜葫??${invalid} 撘萇????瑼??);

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
  const actions = ["Sync JSON ?脰?璅惜?郊", "Fix invalid labels 靽格迤?芰璅惜"];
  const warnings = [];
  if (lm.missingJson > 0) warnings.push(`??${lm.missingJson} 撘萄????芣???JSON 璅?瑼);
  if (lm.unknownLabels > 0) warnings.push(`?菜葫??${lm.unknownLabels} ??券??交??桐葉??交?蝐扎);

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
  const actions = ["Review class balance 瑼Ｚ?憿撟唾﹛摨?, "Go to Augmentation ??敶勗??游?"];
  const warnings = [];
  if (!status.splitComplete) warnings.push("撠?脰? Train / Val / Test ??嚗??餅?璅∪?閮毀嚗?);
  if (status.splitCounts.val === 0) warnings.push("撽???(Val) ?賊???0嚗?????撽?鞈???);

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

  const actions = ["Preview augmentation ?汗?游???", "Apply to Train only 憟?拍??游?", "Go to Training ??璅∪?閮毀"];
  const warnings = ["Val/Test excluded (撽??葫閰阡?銝脰??游?)", "Strong blur may reduce annotation quality"];

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

  const actions = ["Fix readiness checks ??餅???", "Start training ??閮毀瘚?", "View latest run 瑼Ｚ?????"];
  const warnings = [];
  if (!status.trainReady) warnings.push("隢??日??蝝????Dataset?歇?郊 Label?歇撱箇? Split嚗????閮毀??);
  if (gpu === "CPU" || gpu.includes("unavailable") || gpu.includes("Backend")) warnings.push("GPU unavailable (?桀???CPU ????璅∪?嚗?蝺湧漲?扔????);

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
    actions: ["??霅?蝐斗?撠蒂?? Confusion Matrix", "瑼Ｚ??葫憭望??? (Failure cases)"],
    warnings: !status.bestModelExists ? ["?桀?撠?曉撌脰?蝺渡??雿單芋????] : []
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

  const actions = ["Select model ?豢?頛甈?", "Upload test image 銝皜祈岫??", "Run inference ?瑁??桀撐?刻?"];
  const warnings = [];
  if (models.length === 0) warnings.push("no trained weights found (撠?曉隞颱?撌脰?蝺湔???隢?閮毀璅∪?)??);

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
    "?豢? best.pt / last.pt 雿?阮?Ｙ?璅∪???,
    "??桀撐?? preview嚗??脣鞈?憭暹甈～?,
    "敺? API 摰?敺?鈭箏極蝣箄???Export LabelMe / YOLO??
  ];

  const warnings = [
    "P0 UI only嚗???銵??閮颯?,
    "Apply scope ?身??Train only嚗?情??Val/Test??
  ];
  if (models.length === 0) warnings.unshift("?曆??啣?冽芋??隢?摰? Training??);
  if (models.length > 0 && compatibleModels.length === 0) warnings.unshift("?桀?璅∪?隞餃???獢遙???詨捆??);

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
    actions: ["Export ONNX ?臬頝典像?圈蝵脫撘?, "Generate report ?Ｙ? Markdown 閮毀?勗?"],
    warnings: !status.bestModelExists ? ["?⊥?雿單芋????ONNX 撠?撌脣??具?] : []
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
    actions: ["暺??甇瑕閮??亦?甇瑕 Metrics", "?臬撠?霈甇瑞??勗?"],
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
    actions: ["隤踵隤??末閮剖?", "??瘛梯/?漁銝駁?鈭桀漲"],
    warnings: !isHealthy ? ["API 敺垢隡箸??冽?????頞??啣虜??] : []
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
    const guard = statusGuard("warning", "撠頛撠?", ["甇日??舐汗嚗???撌脣??具?], "?? Projects 撱箇?????獢?);
    Object.keys(guards).forEach((key) => guards[key].push(guard));
  }
  if (status.hasProject && !status.hasDataset) {
    guards.labelme.push(statusGuard("warning", "撠?臬鞈???, ["Images folder ?桀?瘝?????], "?? Dataset ?臬???蔣?撟??));
    guards.split.push(statusGuard("warning", "撠?臬鞈???, ["銝撱箇? Train / Val / Test??], "????Dataset ?臬??));
    guards.training.push(statusGuard("danger", "?桀??⊥???閮毀", ["撠?臬鞈???], "?? Dataset ?臬????));
  }
  if (status.hasDataset && !status.labelme.synced) {
    guards.training.push(statusGuard("danger", "?桀??⊥???閮毀", ["撠?郊 LabelMe 璅酉??], "?? LabelMe ??甇?JSON嚗?頧??箄?蝺湔撘?));
    guards.split.push(statusGuard("info", "LabelMe 撠?郊", ["甇日?畾萎??航身摰?split UI嚗?甇??閮毀??敺?LabelMe JSON 頧?摰???], "?? LabelMe ??甇?JSON ?銵???));
  }
  if (status.hasDataset && !status.splitComplete) {
    guards.training.push(statusGuard("danger", "?桀??⊥???閮毀", ["撠撱箇? Train / Val / Test??], "?? Split 撱箇?鞈????));
    guards.augmentation.push(statusGuard("warning", "撠摰? split", ["憟 augmentation ??閬??target split??], "?? Split 撱箇? Train / Val / Test??));
  }
  if (!status.bestModelExists) {
    guards.evaluation.push(statusGuard("warning", "?桀?瘝??航?隡唳芋??, ["撠摰?閮毀???芰??best model??], "摰?閮毀敺??亦? mAP / IoU??));
    guards.export.push(statusGuard("warning", "?桀?瘝??臬?箸芋??, ["撠?曉?雿單芋????], "摰?閮毀敺??臬 PT / ONNX??));
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

// Toast ??Modal ?批
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

