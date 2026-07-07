import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UIShellModularizationStaticTests(unittest.TestCase):
    def test_app_shell_delegates_common_shell_rendering_to_core_modules(self):
        app_js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        header_js = (ROOT / "static" / "core" / "header_status.js").read_text(encoding="utf-8")
        guards_js = (ROOT / "static" / "core" / "page_guards.js").read_text(encoding="utf-8")
        availability_js = (ROOT / "static" / "core" / "action_availability.js").read_text(encoding="utf-8")
        toast_js = (ROOT / "static" / "core" / "toast.js").read_text(encoding="utf-8")
        router_js = (ROOT / "static" / "core" / "router.js").read_text(encoding="utf-8")
        right_panel_js = (ROOT / "static" / "core" / "right_panel.js").read_text(encoding="utf-8")

        self.assertIn('from "./core/header_status.js"', app_js)
        self.assertIn('from "./core/page_guards.js"', app_js)
        self.assertIn('from "./core/action_availability.js"', app_js)
        self.assertIn('from "./core/toast.js"', app_js)
        self.assertIn('from "./core/router.js"', app_js)
        self.assertIn('from "./core/right_panel.js"', app_js)
        self.assertIn("renderHeaderStatusCore();", app_js)
        self.assertIn("renderRightPanelCore(appState.currentPage, status);", app_js)
        self.assertIn("renderPageGuardsCore(appState.currentPage, status);", app_js)
        self.assertIn("updateActionAvailabilityCore(status);", app_js)
        self.assertIn("showToastCore(message);", app_js)
        self.assertIn("showToastCore(`Failed to load projects: ${err.message}`);", app_js)
        self.assertIn("setActivePage(pageId);", app_js)
        self.assertNotIn("function renderHeaderStatus()", app_js)
        self.assertNotIn("function renderRightPanel(pageId, status)", app_js)
        self.assertNotIn("const RIGHT_PANEL_CONFIG", app_js)
        self.assertNotIn("function renderPageGuards(pageId, status)", app_js)
        self.assertNotIn("function updateActionAvailability(status)", app_js)
        self.assertNotIn("function showToast(message)", app_js)

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


if __name__ == "__main__":
    unittest.main()
