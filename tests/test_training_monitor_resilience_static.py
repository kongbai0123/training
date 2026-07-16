import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TrainingMonitorResilienceStaticTests(unittest.TestCase):
    def test_monitor_uses_compact_responsive_status_grid(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        css = (ROOT / "static" / "styles" / "pages" / "training.css").read_text(encoding="utf-8")
        self.assertIn('class="training-status-grid"', html)
        self.assertIn('id="training-monitor-outcome"', html)
        self.assertIn("grid-template-columns: repeat(5, minmax(0, 1fr));", css)
        self.assertIn(".training-monitor-outcome", css)

    def test_monitor_has_http_fallback_and_terminal_status_handling(self):
        script = (ROOT / "static" / "pages" / "training.js").read_text(encoding="utf-8")
        self.assertIn('new Set(["completed", "failed", "stopped"])', script)
        self.assertIn("scheduleTrainingStatusPoll(4000)", script)
        self.assertIn("refreshTrainingStatusFromApi", script)
        self.assertIn("applyTrainingStatusUpdate(JSON.parse(event.data))", script)
        self.assertIn("training.monitor.outcomeEarlyStop", script)

    def test_training_refresh_toast_has_translation_dependency(self):
        bootstrap = (ROOT / "static" / "core" / "bootstrap.js").read_text(encoding="utf-8")
        self.assertIn("  t,\n} from \"../state.js\";", bootstrap)
        self.assertIn('showToastCore(t("common.projectRefreshed"))', bootstrap)


if __name__ == "__main__":
    unittest.main()
