import { eventBus } from "../event_bus.js";
import {
  appState,
  initPreferences,
  applyLanguage,
  getProjectStatus,
} from "../state.js";
import { qs, qsa } from "../utils.js";
import { initGlobalProgressHud } from "../ui/progress_hud.js";
import { renderHeaderStatus as renderHeaderStatusCore } from "./header_status.js";
import { renderPageGuards as renderPageGuardsCore } from "./page_guards.js";
import { updateActionAvailability as updateActionAvailabilityCore } from "./action_availability.js";
import { showToast as showToastCore } from "./toast.js";
import { setActivePage } from "./router.js";
import { renderRightPanel as renderRightPanelCore } from "./right_panel.js";
import { initInfoTooltips } from "./tooltip.js";
import { createProjectLifecycle } from "./project_lifecycle.js";
import {
  initPageModules,
  renderPrimaryPageModules,
  renderSecondaryPageModules,
} from "./page_registry.js";

const {
  bootstrapSession,
  fetchSystemHealth,
  loadProjects,
  openProject,
  saveCurrentProject,
  openHistoryModal,
  closeHistoryModal,
  clearDeletedProject,
} = createProjectLifecycle({ renderAll, navigate });

export async function bootstrapApp() {
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
    clearDeletedProject(projectId);
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
