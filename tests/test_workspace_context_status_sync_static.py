import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkspaceContextStatusSyncStaticTests(unittest.TestCase):
    def test_dynamic_workspace_summary_is_not_overwritten_by_i18n_pass(self):
        index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        right_panel = (ROOT / "static" / "core" / "right_panel.js").read_text(encoding="utf-8")
        i18n = (ROOT / "static" / "state" / "i18n.js").read_text(encoding="utf-8")

        match = re.search(
            r'<div class="workspace-context-summary" id="workspace-context-summary"([^>]*)>',
            index,
        )
        self.assertIsNotNone(match)
        self.assertNotIn("data-i18n", match.group(1))

        self.assertIn('summary.removeAttribute("data-i18n")', right_panel)
        self.assertIn("summary.innerHTML =", right_panel)
        self.assertIn('document.querySelectorAll("[data-i18n]")', i18n)

    def test_shared_renderer_uses_current_project_status_for_every_page(self):
        right_panel = (ROOT / "static" / "core" / "right_panel.js").read_text(encoding="utf-8")
        bootstrap = (ROOT / "static" / "core" / "bootstrap.js").read_text(encoding="utf-8")

        self.assertIn("updateWorkspaceContextSummary(pageId, status, config);", right_panel)
        self.assertIn("const status = getProjectStatus(appState.currentProject);", bootstrap)
        self.assertIn("renderRightPanelCore(appState.currentPage, status);", bootstrap)


if __name__ == "__main__":
    unittest.main()
