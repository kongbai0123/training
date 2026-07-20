import { eventBus } from "../event_bus.js";
import {
  appState,
  applyLanguage,
  t,
  updateLabelMeState,
} from "../state.js";
import { apiFetch } from "../api.js";
import { qs, setText, setHTML, escapeHtml } from "../utils.js";
import {
  loadPageRecommendedConfig,
  syncPageModeForProject,
} from "./page_registry.js";
import { showToast as showToastCore } from "./toast.js";

export function createProjectLifecycle({ renderAll, navigate }) {
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
        device: { has_gpu: false, device_name: "Backend unavailable" },
      };
    } finally {
      clearTimeout(timeoutId);
      renderAll();
    }
  }

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
      await checkCurrentTrainStatus();
      try {
        const models = await apiFetch(`/api/projects/${projectId}/models`);
        appState.models = Array.isArray(models) ? models : [];
      } catch (e) {
        console.warn("Failed to prefetch models:", e.message);
        appState.models = [];
      }
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
    try {
      return await apiFetch(`/api/projects/${projectId}/save`, { method: "POST", suppressToast: true });
    } catch (error) {
      if (error?.status === 404 || error?.status === 405) {
        return apiFetch(`/api/projects/${projectId}`);
      }
      throw error;
    }
  }

  async function checkCurrentTrainStatus() {
    if (!appState.currentProjectId) return;
    try {
      appState.trainingStatus = await apiFetch(`/api/projects/${appState.currentProjectId}/train/status`);
      eventBus.emit("check-training-websocket");
    } catch {
      appState.trainingStatus = null;
    }
  }

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

  function clearDeletedProject(projectId) {
    if (appState.currentProjectId !== projectId) return;
    appState.currentProjectId = null;
    appState.currentProject = null;
    appState.trainingStatus = null;
    updateLabelMeState();
    if (appState.wsConn) {
      appState.wsConn.close();
      appState.wsConn = null;
    }
  }

  return {
    bootstrapSession,
    fetchSystemHealth,
    loadProjects,
    openProject,
    saveCurrentProject,
    openHistoryModal,
    closeHistoryModal,
    clearDeletedProject,
    checkCurrentTrainStatus,
  };
}
