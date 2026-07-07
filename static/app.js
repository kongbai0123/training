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
import { initGlobalProgressHud } from "./ui/progress_hud.js";
import { renderHeaderStatus as renderHeaderStatusCore } from "./core/header_status.js";
import { renderPageGuards as renderPageGuardsCore } from "./core/page_guards.js";
import { updateActionAvailability as updateActionAvailabilityCore } from "./core/action_availability.js";
import { showToast as showToastCore } from "./core/toast.js";
import { setActivePage } from "./core/router.js";
import { renderRightPanel as renderRightPanelCore } from "./core/right_panel.js";

// Page modules.
import { initDashboard, renderDashboard } from "./pages/dashboard.js";
import { initProjects, renderProjectsPage } from "./pages/projects.js?v=20260630-class-batch-infer";
import { initDataset, renderDatasetPage } from "./pages/dataset.js?v=20260630-progress-hud";
import { initLabelMe, renderLabelMeManager } from "./pages/labelme.js";
import { initSplit, renderSplitPage } from "./pages/split.js";
import { initAugmentation, renderAugmentationPage } from "./pages/augmentation.js?v=20260625-augmentation-p0";
import { initTraining, renderTrainingMonitor, loadRecommendedConfig } from "./pages/training.js?v=20260702-cnn-eval-polish2";
import { initTrainingModeSidebar, renderTrainingModeSidebar, renderTrainingWorkspace, syncTrainingModeForProject, trainingModeState, isRnnTrainingWorkspaceActive } from "./pages/training_modes.js?v=20260706-rnn-pc-catalog";
import { initEvaluation, renderEvaluationPage } from "./pages/evaluation.js?v=20260702-cnn-eval-polish2";
import { initModelCompare, renderModelComparePage } from "./pages/model_compare.js?v=20260630-ui-init-fix";
import { initInference, renderInferencePage } from "./pages/inference.js?v=20260702-model-scroll-bounds";
import { initAutoLabeling, renderAutoLabelingPage } from "./pages/auto_labeling.js?v=20260703-auto-workbench-rules";
import { initExport, renderExportPage } from "./pages/export.js?v=20260701-xgb-eval-final";
import { initSettings, renderSettingsPage } from "./pages/settings.js";

async function bootstrapApp() {
  initPreferences();
  initGlobalProgressHud();
  bindGlobalNavigation();
  bindInfoTooltips();

  // Initialize page modules.
  initDashboard();
  initProjects();
  initDataset();
  initLabelMe();
  initSplit();
  initAugmentation();
  initTraining();
  initEvaluation();
  initModelCompare();
  initInference();
  initAutoLabeling();
  initExport();
  initSettings();
  initTrainingModeSidebar();

  await bootstrapSession();

  // Fetch system health before the first render.
  fetchSystemHealth();

  // Start with an empty workspace. Users explicitly open projects from Browse History.
  await loadProjects({ autoOpenLatest: false });
  navigate("dashboard");
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    bootstrapApp().catch((err) => console.error("Application bootstrap failed:", err));
  }, { once: true });
} else {
  bootstrapApp().catch((err) => console.error("Application bootstrap failed:", err));
}

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

// Bind global floating tooltips.
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
      if (btn.dataset.modeNav) return;
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

  // History modal actions.
  qs("#btn-header-save-project")?.addEventListener("click", saveCurrentProject);
  qs("#btn-header-history")?.addEventListener("click", openHistoryModal);
  qs("#btn-close-history")?.addEventListener("click", closeHistoryModal);
  qs("#project-history-modal")?.addEventListener("click", (event) => {
    if (event.target.id === "project-history-modal") closeHistoryModal();
  });

  // Event bus handlers.
  eventBus.on("state-changed", () => {
    renderAll();
  });

  eventBus.on("toast", (message) => {
    showToastCore(message);
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
      await openProject(options.openProjectId, { page: options.page || "dashboard" });
    }
  });

  eventBus.on("refresh-project", async () => {
    await loadProjects({ autoOpenLatest: false });
    if (appState.currentProjectId) {
      await openProject(appState.currentProjectId, { stayOnPage: true });
    }
    showToastCore("Project refreshed.");
  });

  eventBus.on("project-deleted", async (projectId) => {
    if (appState.currentProjectId === projectId) {
      appState.currentProjectId = null;
      appState.currentProject = null;
      appState.trainingStatus = null;
      updateLabelMeState();
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
  setActivePage(pageId);
  renderAll();
}

function renderAll() {
  const status = getProjectStatus(appState.currentProject);
  
  renderHeaderStatusCore();

  // Render page modules.
  renderDashboard(status);
  renderRightPanelCore(appState.currentPage, status);
  renderPageGuardsCore(appState.currentPage, status);
  renderDatasetPage(status);
  renderLabelMeManager(status);
  renderSplitPage(status);
  renderAugmentationPage(status);
  renderTrainingMonitor();
  renderTrainingModeSidebar();
  renderTrainingWorkspace();
  renderEvaluationPage(status);
  renderModelComparePage();
  renderInferencePage(status);
  renderAutoLabelingPage(status);
  renderExportPage(status);
  renderSettingsPage();
  renderProjectsPage();

  updateActionAvailabilityCore(status);
  applyLanguage(appState.settings.language);
}

// Load project list.
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
    showToastCore(`Failed to load projects: ${err.message}`);
    renderAll();
  }
}

async function openProject(projectId, options = {}) {
  if (!projectId) return;
  try {
    appState.currentProject = await apiFetch(`/api/projects/${projectId}`);
    appState.currentProjectId = projectId;
    appState.currentProjectClasses = [...(appState.currentProject?.class_names || [])];
    syncTrainingModeForProject(appState.currentProject, options.page || appState.currentPage);
    updateLabelMeState();
    // Close any existing monitor websocket.
    await checkCurrentTrainStatus();
    // Load project details and sync state.
    try {
      const models = await apiFetch(`/api/projects/${projectId}/models`);
      appState.models = Array.isArray(models) ? models : [];
    } catch (e) {
      console.warn("Failed to prefetch models:", e.message);
      appState.models = [];
    }
    // Start project monitor.
    await loadRecommendedConfig();
    renderAll();
    if (!options.stayOnPage) navigate(options.page || "dashboard");
  } catch (err) {
    showToastCore(`Failed to open project: ${err.message}`);
  }
}

async function saveCurrentProject() {
  const projectId = appState.currentProjectId;
  if (!projectId) {
    showToastCore(t("headerSaveNoProject"));
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
    updateLabelMeState();
    await checkCurrentTrainStatus();
    renderAll();
    showToastCore(t("headerSaveDone"));
  } catch (err) {
    showToastCore(t("headerSaveFailed", { message: err.message }));
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
    // Close stale monitor websocket before reconnecting.
    eventBus.emit("check-training-websocket");
  } catch {
    appState.trainingStatus = null;
  }
}

// Toast ??Modal ?批
async function openHistoryModal() {
  const modal = qs("#project-history-modal");
  if (modal) modal.hidden = false;
  setText("#project-history-result-count", "Loading projects...");
  setHTML("#modal-project-list", `<div class="empty-state">Loading project history...</div>`);
  try {
    appState.projects = await apiFetch("/api/projects");
    qs("#api-status-dot")?.classList.add("online");
    qs("#api-status-dot")?.classList.remove("offline");
    renderAll();
    eventBus.emit("render-project-history-modal");
  } catch (err) {
    qs("#api-status-dot")?.classList.add("offline");
    setText("#project-history-result-count", "Load failed");
    setHTML("#modal-project-list", `<div class="empty-state">Failed to load project history: ${escapeHtml(err.message)}</div>`);
  }
}

function closeHistoryModal() {
  const modal = qs("#project-history-modal");
  if (modal) modal.hidden = true;
}

