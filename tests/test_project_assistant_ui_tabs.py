import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProjectAssistantUiTabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        cls.script = (ROOT / "static" / "pages" / "project_assistant_impl.js").read_text(encoding="utf-8")
        cls.styles = (ROOT / "static" / "styles" / "pages" / "project_assistant.css").read_text(encoding="utf-8")

    def test_drawer_exposes_three_primary_tabs(self):
        for tab in ("qa", "sources", "settings"):
            self.assertIn(f'data-assistant-tab="{tab}"', self.index)
            self.assertIn(f'data-assistant-tab-panel="{tab}"', self.index)

    def test_tab_switch_hides_non_active_panels(self):
        self.assertIn("function activateAssistantTab(tabId)", self.script)
        self.assertIn("panel.dataset.assistantTabPanel !== assistantState.activeTab", self.script)
        self.assertIn("[data-assistant-tab-panel][hidden]", self.styles)

    def test_internal_sandbox_and_evaluation_do_not_occupy_primary_ui(self):
        self.assertIn("assistant-sandbox-panel assistant-legacy-panel", self.index)
        self.assertIn("assistant-evaluation-panel assistant-legacy-panel", self.index)
        self.assertIn("assistant-agent-panel assistant-legacy-panel", self.index)
        self.assertIn(".assistant-legacy-panel", self.styles)

    def test_status_strip_is_project_and_context_oriented(self):
        self.assertIn('id="rag-status-project"', self.index)
        self.assertIn('id="rag-status-context"', self.index)
        self.assertNotIn('id="rag-status-chunks"', self.index)


if __name__ == "__main__":
    unittest.main()
