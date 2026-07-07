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
import { initInfoTooltips } from "./core/tooltip.js";
import {
  initPageModules,
  loadPageRecommendedConfig,
  renderPrimaryPageModules,
  renderSecondaryPageModules,
  syncPageModeForProject,
} from "./core/page_registry.js";

async function bootstrapApp() {
  initPreferences();
  initGlobalProgressHud();
  bindGlobalNavigation();
  initInfoTooltips();

  initPageModules();

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

  renderPrimaryPageModules(status);
  renderRightPanelCore(appState.currentPage, status);
  renderPageGuardsCore(appState.currentPage, status);
  renderSecondaryPageModules(status);

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
    syncPageModeForProject(appState.currentProject, options.page || appState.currentPage);
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
    await loadPageRecommendedConfig();
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

