from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_rnn_start_action_is_only_in_training_panel_and_not_readiness_locked():
    html = read("static/index.html")
    modes = read("static/pages/training_modes.js")

    assert html.count('id="rnn-start-disabled"') == 1
    training_panel = html.index('id="rnn-training-panel"')
    start_button = html.index('id="rnn-start-disabled"')
    evaluation_panel = html.index('id="rnn-evaluation-panel"')
    assert training_panel < start_button < evaluation_panel
    assert 'id="rnn-start-disabled" disabled' not in html
    assert "button.disabled = operationBusy" in modes
    assert 'button.removeAttribute("data-requires")' in modes
    assert 't("rnn.training.blocker.settings")' in read("static/pages/rnn_readiness_helpers.js")


def test_rnn_live_monitor_uses_task_specific_metrics():
    html = read("static/index.html")
    helpers = read("static/pages/rnn_intelligence_helpers.js")
    modes = read("static/pages/training_modes.js")

    assert 'id="rnn-live-monitor"' in html
    assert 'id="rnn-monitor-quality-chart"' in html
    assert 'id="rnn-monitor-loss-chart"' in html
    for metric in ("val/accuracy", "val/macro_f1", "val/precision", "val/recall", "val/mae", "val/rmse"):
        assert metric in helpers
    assert "buildRnnLiveMonitorViewModel(appState.trainingStatus" in modes
    assert "Chart.getChart(canvas)?.destroy()" in modes
    assert 'TrainingStateStore.set_field(project_id, "task_type"' in read("src/training/backends/rnn_backend.py")


def test_training_heartbeat_updates_monitor_without_rerendering_the_whole_app():
    training = read("static/pages/training.js")
    modes = read("static/pages/training_modes.js")
    update_block = training.split("function applyTrainingStatusUpdate(data)", 1)[1].split(
        "function scheduleTrainingStatusPoll", 1
    )[0]

    assert 'eventBus.emit("training-status-changed"' in update_block
    assert 'eventBus.emit("state-changed")' not in update_block
    assert 'eventBus.on("training-status-changed"' in modes
    assert "rnnMonitorChartSignatures" in modes
    assert "if (hasSeries && rnnMonitorChartSignatures.get(canvasId) === signature) return;" in modes


def test_rnn_evaluation_has_smart_advice_and_true_svg_downloads():
    html = read("static/index.html")
    helpers = read("static/pages/rnn_intelligence_helpers.js")
    modes = read("static/pages/training_modes.js")

    assert 'id="rnn-eval-intelligence"' in html
    assert 'id="rnn-intelligence-score"' in html
    assert 'data-rnn-chart-download="score"' in html
    assert 'data-rnn-chart-download="loss"' in html
    assert 'data-rnn-chart-download="diagnostic"' in html
    assert "buildRnnSmartAssessment" in helpers
    assert "buildRnnLineChartSvg" in helpers
    assert "buildRnnBarChartSvg" in helpers
    assert "buildRnnDiagnosticSvg" in helpers
    assert 'xmlns="http://www.w3.org/2000/svg"' in helpers
    assert "data:image/png" not in helpers
    assert "new Blob([svg], { type: \"image/svg+xml;charset=utf-8\" })" in modes


def test_rnn_tooltip_translations_no_longer_fall_back_to_english():
    zh = read("static/state/i18n/zh-TW.js")
    modes = read("static/pages/training_modes.js")
    for key in (
        "rnn.schemaWizard.taskTooltip",
        "rnn.schemaWizard.targetTooltip",
        "rnn.schemaWizard.timeTooltip",
        "rnn.schemaWizard.sequenceTooltip",
        "rnn.training.gradientClipTooltip",
        "rnn.modelTooltip.lstm",
    ):
        assert f'"{key}"' in zh
    assert 'eventBus.on("language-changed"' in modes
    assert "syncRnnModelSelection();" in modes


def test_metrics_endpoint_supplies_training_context_for_assessment():
    route = read("src/api/routes/training_runs.py")
    assert 'payload.setdefault("train_config", config_payload)' in route
    assert 'payload.setdefault("run_summary", summary_payload)' in route
