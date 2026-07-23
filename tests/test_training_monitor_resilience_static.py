import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TrainingMonitorResilienceStaticTests(unittest.TestCase):
    def test_training_page_keeps_compact_monitor_and_global_progress(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "static" / "pages" / "training.js").read_text(encoding="utf-8")
        self.assertIn('id="cnn-training-monitor"', html)
        self.assertIn('id="training-monitor-outcome"', html)
        self.assertIn('class="panel-section training-monitor-panel"', html)
        for element_id in (
            "train-status-label",
            "train-progress-text",
            "train-elapsed-time",
            "train-stop-reason",
            "training-monitor-progress-bar",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("formatTrainingDuration(getTrainingElapsedSeconds(trainState))", script)
        self.assertIn("updateGlobalTrainingProgress(trainState, progressPercent, showMonitor);", script)
        self.assertIn("if (isRunning || isStopping) {\n    const liveChartData", script)

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
        self.assertIn("run.run_id === preferredRunId && run.metrics_available !== false", script)
        self.assertIn("requestId !== metricLoadRequestId", script)
        self.assertIn("latestRun.run_id === metricLoadInFlightRunId", script)

    def test_training_page_restores_latest_available_run_per_project(self):
        script = (ROOT / "static" / "pages" / "training.js").read_text(encoding="utf-8")
        self.assertIn("syncTrainingMetricsProjectScope();", script)
        self.assertIn("loadedMetricsProjectId === projectId", script)
        self.assertIn("runs.find((run) => run.metrics_available !== false)", script)
        self.assertIn("projectId !== appState.currentProjectId", script)

    def test_training_page_uses_native_scale_separate_charts_in_three_by_two_grid(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "static" / "pages" / "training.js").read_text(encoding="utf-8")
        css = (ROOT / "static" / "styles" / "pages" / "training.css").read_text(encoding="utf-8")
        self.assertIn('id="metrics-chart-grid"', html)
        self.assertIn('data-scale-mode="native"', html)
        self.assertIn('class="panel-section training-chart-card"', html)
        self.assertNotIn('id="metrics-chart-canvas"', html)
        self.assertNotIn('id="metrics-chart-tabs"', html)
        self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr));", css)
        self.assertIn("buildCnnMetricChartDefinitions(raw)", script)
        self.assertIn(".slice(0, 6)", script)
        self.assertIn('beginAtZero: false', script)

    def test_metric_charts_update_once_per_new_epoch_and_reload_final_run(self):
        script = (ROOT / "static" / "pages" / "training.js").read_text(encoding="utf-8")
        self.assertIn("liveRunId !== lastRenderedMetricRunId || liveEpochCount !== lastRenderedMetricEpochCount", script)
        self.assertIn('lastRenderedMetricEpochCount = liveEpochCount', script)
        self.assertIn('TERMINAL_TRAINING_STATUSES.has(data.status) && previousStatus !== data.status', script)
        self.assertIn('lastLoadedRunId = null;', script)
        self.assertIn('loadLatestRunMetricsOnce();', script)

    def test_yolo_monitor_derives_f1_for_the_sixth_native_metric_chart(self):
        script = (ROOT / "static" / "pages" / "training.js").read_text(encoding="utf-8")
        self.assertIn('"metrics/f1(M)": wsF1', script)
        self.assertIn('function metricF1(precision, recall)', script)
        self.assertIn('[`metrics/f1(${suffix})`, "F1"]', script)
        self.assertLess(
            script.index('["train/box_loss", "Train Box Loss"]'),
            script.index('["train/seg_loss", "Train Seg Loss"]'),
        )

    def test_torchvision_segmentation_metrics_are_available_to_the_training_dashboard(self):
        script = (ROOT / "static" / "pages" / "training.js").read_text(encoding="utf-8")
        self.assertIn('["val/mean_iou", "Mean IoU"]', script)
        self.assertIn('["val/dice", "Dice"]', script)
        self.assertIn('["val/pixel_accuracy", "Pixel Accuracy"]', script)

    def test_augmentation_actions_are_below_settings_summary(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        css = (ROOT / "static" / "styles" / "pages" / "augmentation.css").read_text(encoding="utf-8")
        settings_start = html.index('id="aug-settings-panel"')
        summary_start = html.index('class="aug-quantity-stat"', settings_start)
        preview_start = html.index('aug-live-preview-card', settings_start)
        for button_id in ("btn-reset-aug", "btn-preview-aug", "btn-apply-aug"):
            self.assertEqual(html.count(f'id="{button_id}"'), 1)
            button_position = html.index(f'id="{button_id}"')
            self.assertLess(summary_start, button_position)
            self.assertLess(button_position, preview_start)
        self.assertIn(".aug-apply-row", css)

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
