import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TrainingMonitorResilienceStaticTests(unittest.TestCase):
    def test_training_page_removes_duplicate_metric_monitor_but_keeps_global_progress(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "static" / "pages" / "training.js").read_text(encoding="utf-8")
        self.assertNotIn('class="training-status-grid"', html)
        self.assertNotIn('id="training-monitor-outcome"', html)
        self.assertNotIn('class="training-monitor-panel"', html)
        self.assertIn("updateGlobalTrainingProgress(trainState, progressPercent, showMonitor);", script)

    def test_monitor_has_http_fallback_and_terminal_status_handling(self):
        script = (ROOT / "static" / "pages" / "training.js").read_text(encoding="utf-8")
        self.assertIn('new Set(["completed", "failed", "stopped"])', script)
        self.assertIn("scheduleTrainingStatusPoll(4000)", script)
        self.assertIn("refreshTrainingStatusFromApi", script)
        self.assertIn("applyTrainingStatusUpdate(JSON.parse(event.data))", script)
        self.assertIn("training.monitor.outcomeEarlyStop", script)

    def test_metrics_dashboard_prefers_the_active_run_over_name_sort_order(self):
        script = (ROOT / "static" / "pages" / "training.js").read_text(encoding="utf-8")
        self.assertIn(
            "appState.trainingStatus?.run_id || appState.currentProject?.current?.training_run_id",
            script,
        )
        self.assertIn("runs.find((run) => run.run_id === preferredRunId) || runs[0]", script)
        self.assertIn("requestId !== metricLoadRequestId", script)
        self.assertIn("latestRun.run_id === metricLoadInFlightRunId", script)

    def test_training_page_defers_metric_charts_to_evaluation(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('id="metrics-chart-grid"', html)
        self.assertNotIn('class="training-chart-card"', html)
        self.assertNotIn('id="metrics-chart-canvas"', html)
        self.assertIn('id="rnn-evaluation-panel"', html)
        self.assertIn('id="page-evaluation"', html)

    def test_augmentation_actions_are_below_settings_summary(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        css = (ROOT / "static" / "styles" / "pages" / "augmentation.css").read_text(encoding="utf-8")
        settings_start = html.index('id="aug-settings-panel"')
        summary_start = html.index('class="aug-output-summary"', settings_start)
        preview_start = html.index('class="augmentation-preview-column"', settings_start)
        for button_id in ("btn-reset-aug", "btn-preview-aug", "btn-apply-aug"):
            self.assertEqual(html.count(f'id="{button_id}"'), 1)
            button_position = html.index(f'id="{button_id}"')
            self.assertLess(summary_start, button_position)
            self.assertLess(button_position, preview_start)
        self.assertIn(".aug-settings-actions", css)

    def test_training_scroll_regions_keep_context_visible(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        training_css = (ROOT / "static" / "styles" / "pages" / "training.css").read_text(encoding="utf-8")
        rnn_css = (ROOT / "static" / "styles" / "pages" / "rnn_training.css").read_text(encoding="utf-8")
        self.assertIn('class="training-scroll-title"', html)
        self.assertIn(".training-scroll-table .data-table thead th", training_css)
        self.assertIn(".training-scroll-title", training_css)
        self.assertIn("position: sticky;", training_css)
        self.assertIn(".rnn-preview-table th", rnn_css)

    def test_training_refresh_toast_has_translation_dependency(self):
        bootstrap = (ROOT / "static" / "core" / "bootstrap.js").read_text(encoding="utf-8")
        self.assertIn("  t,\n} from \"../state.js\";", bootstrap)
        self.assertIn('showToastCore(t("common.projectRefreshed"))', bootstrap)


if __name__ == "__main__":
    unittest.main()
