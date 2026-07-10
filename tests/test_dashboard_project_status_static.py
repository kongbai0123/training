import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DashboardProjectStatusStaticTests(unittest.TestCase):
    def read(self, *parts):
        return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")

    def test_dashboard_connects_task_aware_status_strip(self):
        dashboard = self.read("static", "pages", "dashboard.js")
        status_strip = self.read("static", "core", "project_status_strip.js")

        self.assertIn("resolveDashboardProjectMode", dashboard)
        self.assertIn("buildProjectStatusView", dashboard)
        self.assertIn("renderProjectStatusStrip", dashboard)
        self.assertIn("trainingModeState.rnn", dashboard)
        self.assertIn('data-ui-smoke="project-status-strip"', status_strip)
        self.assertIn('data-rnn-target=', status_strip)

    def test_status_strip_is_task_specific_and_does_not_restore_legacy_grid(self):
        status_strip = self.read("static", "core", "project_status_strip.js")
        dashboard_css = self.read("static", "styles", "pages", "dashboard.css")

        self.assertIn("buildCnnPhases", status_strip)
        self.assertIn("buildRnnPhases", status_strip)
        self.assertIn('dashboard.status.phase.cnn.annotation', status_strip)
        self.assertIn('dashboard.status.phase.rnn.schema', status_strip)
        self.assertIn("grid-template-columns: repeat(4, minmax(0, 1fr));", dashboard_css)
        self.assertNotIn('class="workflow-grid"', status_strip)
        self.assertNotIn('class="progress-track"', status_strip)

    def test_status_catalog_keys_exist_in_both_languages(self):
        en = self.read("static", "state", "i18n", "en.js")
        zh = self.read("static", "state", "i18n", "zh-TW.js")
        for key in (
            "dashboard.status.title",
            "dashboard.status.readySummary",
            "dashboard.status.phase.cnn.data",
            "dashboard.status.phase.rnn.schema",
            "dashboard.status.action.configureSchema",
        ):
            self.assertIn(f'"{key}"', en)
            self.assertIn(f'"{key}"', zh)


if __name__ == "__main__":
    unittest.main()
