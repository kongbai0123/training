from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_onboarding_has_four_explicit_steps_and_panels():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    for step in range(1, 5):
        assert f'data-onboarding-step="{step}"' in html
        assert f'data-onboarding-panel="{step}"' in html
    assert 'id="btn-onboarding-next"' in html
    assert 'id="btn-onboarding-back"' in html


def test_onboarding_persists_user_preferences_and_filters_tasks():
    source = (ROOT / "static" / "core" / "model_setup.js").read_text(encoding="utf-8")
    assert "vts-onboarding-preferences" in source
    assert "applyLanguage(event.target.value)" in source
    assert "applyTheme(event.target.value)" in source
    assert 'selectedTask === "sequence"' in source
    assert "resolveModelScale" in source


def test_model_scale_labels_cover_supported_size_suffixes():
    source = (ROOT / "static" / "state" / "i18n" / "en.js").read_text(encoding="utf-8")
    for scale in ("nano", "small", "medium", "large", "xlarge"):
        assert f'"modelSetup.scale.{scale}.name"' in source
        assert f'"modelSetup.scale.{scale}.help"' in source


def test_onboarding_layout_has_responsive_step_and_task_grids():
    css = (ROOT / "static" / "styles" / "pages" / "model_setup.css").read_text(encoding="utf-8")
    assert ".model-setup-step-nav" in css
    assert ".model-setup-task-filter" in css
    assert "repeat(4, minmax(0, 1fr))" in css
    assert "@media (max-width: 760px)" in css
