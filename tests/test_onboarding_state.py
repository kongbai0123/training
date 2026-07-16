import json

from src.onboarding_state import complete_onboarding, get_onboarding_state


def test_onboarding_defaults_to_pending_when_marker_is_missing(tmp_path):
    state = get_onboarding_state(tmp_path / "onboarding.json")
    assert state["initial_setup_completed"] is False
    assert state["completed_at"] is None


def test_onboarding_completion_is_persisted_outside_browser_storage(tmp_path):
    path = tmp_path / "config" / "onboarding.json"
    completed = complete_onboarding("skipped", path)

    assert completed["initial_setup_completed"] is True
    assert get_onboarding_state(path)["outcome"] == "skipped"
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 1
