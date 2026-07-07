import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UIShellModularizationStaticTests(unittest.TestCase):
    def test_state_shell_delegates_i18n_dictionary_and_fallback_to_state_module(self):
        state_js = (ROOT / "static" / "state.js").read_text(encoding="utf-8")
        i18n_js = (ROOT / "static" / "state" / "i18n.js").read_text(encoding="utf-8")

        self.assertIn('from "./state/i18n.js"', state_js)
        self.assertIn('export { i18n } from "./state/i18n.js";', state_js)
        self.assertIn("return translateI18n(key, appState.settings.language, params);", state_js)
        self.assertIn("applyLanguageToDocument({", state_js)
        self.assertNotIn("export const i18n = {", state_js)
        self.assertNotIn("let zhFallbackObserver", state_js)
        self.assertNotIn("configureI18nFallback", state_js)

        self.assertIn("export const i18n = {", i18n_js)
        self.assertIn("export function translate", i18n_js)
        self.assertIn("export function applyLanguageToDocument", i18n_js)
        self.assertIn("let zhFallbackObserver", i18n_js)
        self.assertIn("configureI18nFallback", i18n_js)

    def test_app_shell_delegates_common_shell_rendering_to_core_modules(self):
        app_js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        header_js = (ROOT / "static" / "core" / "header_status.js").read_text(encoding="utf-8")
        guards_js = (ROOT / "static" / "core" / "page_guards.js").read_text(encoding="utf-8")
        availability_js = (ROOT / "static" / "core" / "action_availability.js").read_text(encoding="utf-8")
        toast_js = (ROOT / "static" / "core" / "toast.js").read_text(encoding="utf-8")
        router_js = (ROOT / "static" / "core" / "router.js").read_text(encoding="utf-8")
        right_panel_js = (ROOT / "static" / "core" / "right_panel.js").read_text(encoding="utf-8")
        page_registry_js = (ROOT / "static" / "core" / "page_registry.js").read_text(encoding="utf-8")
        tooltip_js = (ROOT / "static" / "core" / "tooltip.js").read_text(encoding="utf-8")
        project_lifecycle_js = (ROOT / "static" / "core" / "project_lifecycle.js").read_text(encoding="utf-8")

        self.assertIn('from "./core/header_status.js"', app_js)
        self.assertIn('from "./core/page_guards.js"', app_js)
        self.assertIn('from "./core/action_availability.js"', app_js)
        self.assertIn('from "./core/toast.js"', app_js)
        self.assertIn('from "./core/router.js"', app_js)
        self.assertIn('from "./core/right_panel.js"', app_js)
        self.assertIn('from "./core/tooltip.js"', app_js)
        self.assertIn('from "./core/project_lifecycle.js"', app_js)
        self.assertIn('from "./core/page_registry.js"', app_js)
        self.assertIn("createProjectLifecycle({ renderAll, navigate });", app_js)
        self.assertIn("initPageModules();", app_js)
        self.assertIn("initInfoTooltips();", app_js)
        self.assertIn("renderHeaderStatusCore();", app_js)
        self.assertIn("renderPrimaryPageModules(status);", app_js)
        self.assertIn("renderRightPanelCore(appState.currentPage, status);", app_js)
        self.assertIn("renderPageGuardsCore(appState.currentPage, status);", app_js)
        self.assertIn("renderSecondaryPageModules(status);", app_js)
        self.assertIn("updateActionAvailabilityCore(status);", app_js)
        self.assertIn("showToastCore(message);", app_js)
        self.assertIn("setActivePage(pageId);", app_js)
        self.assertNotIn('from "./pages/dashboard.js"', app_js)
        self.assertNotIn('from "./pages/training.js', app_js)
        self.assertNotIn("async function bootstrapSession", app_js)
        self.assertNotIn("async function loadProjects", app_js)
        self.assertNotIn("async function openProject", app_js)
        self.assertNotIn("async function saveCurrentProject", app_js)
        self.assertNotIn("async function requestProjectSave", app_js)
        self.assertNotIn("async function checkCurrentTrainStatus", app_js)
        self.assertNotIn("function renderHeaderStatus()", app_js)
        self.assertNotIn("function renderRightPanel(pageId, status)", app_js)
        self.assertNotIn("const RIGHT_PANEL_CONFIG", app_js)
        self.assertNotIn("function renderPageGuards(pageId, status)", app_js)
        self.assertNotIn("function updateActionAvailability(status)", app_js)
        self.assertNotIn("function showToast(message)", app_js)
        self.assertNotIn("function bindInfoTooltips()", app_js)
        self.assertNotIn("renderTooltipContent", app_js)

        self.assertIn("export function renderHeaderStatus", header_js)
        self.assertIn("#header-gpu-value", header_js)
        self.assertIn("#header-project-title", header_js)

        self.assertIn("export function renderPageGuards", guards_js)
        self.assertIn("isRnnTrainingWorkspaceActive(pageId)", guards_js)
        self.assertIn("Training blocked", guards_js)

        self.assertIn("export function updateActionAvailability", availability_js)
        self.assertIn('qsa(".guarded")', availability_js)
        self.assertIn("#btn-start-train", availability_js)

        self.assertIn("export function showToast", toast_js)
        self.assertIn("#toast", toast_js)
        self.assertIn("window.setTimeout", toast_js)

        self.assertIn("export function setActivePage", router_js)
        self.assertIn('qsa(".sidebar-item")', router_js)
        self.assertIn('qsa(".page")', router_js)
        self.assertIn('pageId || "dashboard"', router_js)

        self.assertIn("export function renderRightPanel", right_panel_js)
        self.assertIn("const RIGHT_PANEL_CONFIG", right_panel_js)
        self.assertIn("function buildRnnTrainingRightPanel", right_panel_js)
        self.assertIn("RNN Context", right_panel_js)

        self.assertIn("export function initPageModules", page_registry_js)
        self.assertIn("export function renderPrimaryPageModules", page_registry_js)
        self.assertIn("export function renderSecondaryPageModules", page_registry_js)
        self.assertIn("export function syncPageModeForProject", page_registry_js)
        self.assertIn("export function loadPageRecommendedConfig", page_registry_js)
        self.assertIn("renderDashboard(status);", page_registry_js)
        self.assertIn("renderTrainingWorkspace();", page_registry_js)

        self.assertIn("export function initInfoTooltips", tooltip_js)
        self.assertIn("#floating-tooltip", tooltip_js)
        self.assertIn(".info-icon[data-tooltip]", tooltip_js)
        self.assertIn("escapeHtml", tooltip_js)
        self.assertIn('window.addEventListener("resize"', tooltip_js)

        self.assertIn("export function createProjectLifecycle", project_lifecycle_js)
        self.assertIn("async function bootstrapSession", project_lifecycle_js)
        self.assertIn("async function loadProjects", project_lifecycle_js)
        self.assertIn("async function openProject", project_lifecycle_js)
        self.assertIn("async function saveCurrentProject", project_lifecycle_js)
        self.assertIn("async function requestProjectSave", project_lifecycle_js)
        self.assertIn("async function checkCurrentTrainStatus", project_lifecycle_js)
        self.assertIn("showToastCore(`Failed to load projects: ${err.message}`);", project_lifecycle_js)
        self.assertIn("syncPageModeForProject(appState.currentProject", project_lifecycle_js)
        self.assertIn("await loadPageRecommendedConfig();", project_lifecycle_js)
        self.assertIn("clearDeletedProject", project_lifecycle_js)


if __name__ == "__main__":
    unittest.main()
