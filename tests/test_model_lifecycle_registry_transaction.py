import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.model_lifecycle_registry import ModelLifecycleRegistry
from src.project_layout import ProjectLayout


def _build_transaction_state(tmp_path: Path):
    project_dir = tmp_path / "projects" / "project-transaction"
    ProjectLayout(project_dir, {"layout": {"version": "v3", "mode": "v3"}}).ensure_v3_tree()
    project = {
        "project_id": "project-transaction",
        "dataset_path": (project_dir / "dataset").as_posix(),
        "layout": {"version": "v3", "mode": "v3"},
        "task_type": "tabular_classification",
        "current": {"best_model_id": "run-old::best"},
        "updated_at": "2026-08-25T00:00:00",
    }
    registry_path = ModelLifecycleRegistry._path(project)
    registry = {
        "schema_version": "2.0",
        "versions": [
            {
                "model_id": "run-old::best",
                "version_number": 1,
                "version": "v1",
                "task_type": "tabular_classification",
                "status": "production",
                "updated_at": "2026-08-25T00:00:00",
            },
            {
                "model_id": "run-new::best",
                "version_number": 2,
                "version": "v2",
                "task_type": "tabular_classification",
                "status": "validated",
                "updated_at": "2026-08-25T00:01:00",
            },
        ],
        "events": [
            {
                "event": "status_changed",
                "model_id": "run-old::best",
                "from": "validated",
                "to": "production",
                "at": "2026-08-25T00:00:00",
            }
        ],
    }
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    return project, registry_path


@pytest.mark.parametrize("failure_mode", ["false", "exception"])
def test_production_transition_keeps_registry_and_project_unchanged_when_project_save_fails(
    tmp_path: Path,
    failure_mode: str,
):
    project, registry_path = _build_transaction_state(tmp_path)
    project_before = copy.deepcopy(project)
    registry_before = json.loads(registry_path.read_text(encoding="utf-8"))

    def fail_save(_project_id, project_data):
        project_data["updated_at"] = "mutated-by-failed-save"
        if failure_mode == "exception":
            raise OSError("simulated write failure")
        return False

    with patch.object(ModelLifecycleRegistry, "list_versions", return_value={}), patch(
        "src.model_lifecycle_registry.ProjectManager.save_project",
        side_effect=fail_save,
    ) as save_project:
        with pytest.raises(RuntimeError, match="Unable to update the project's production model"):
            ModelLifecycleRegistry.transition(
                project["project_id"],
                project,
                "run-new::best",
                "production",
            )

    save_project.assert_called_once()
    assert project == project_before
    assert json.loads(registry_path.read_text(encoding="utf-8")) == registry_before


def test_registry_save_failure_persists_exact_pre_transition_project_state(tmp_path: Path):
    project, registry_path = _build_transaction_state(tmp_path)
    project_before = copy.deepcopy(project)
    registry_before = json.loads(registry_path.read_text(encoding="utf-8"))
    persisted_project_states = []

    def capture_save(_project_id, project_data):
        persisted_project_states.append(copy.deepcopy(project_data))
        return True

    with patch.object(ModelLifecycleRegistry, "list_versions", return_value={}), patch.object(
        ModelLifecycleRegistry,
        "_save",
        side_effect=OSError("simulated registry write failure"),
    ), patch(
        "src.model_lifecycle_registry.ProjectManager.save_project",
        side_effect=capture_save,
    ):
        with pytest.raises(RuntimeError, match="model lifecycle registry.*rolled back"):
            ModelLifecycleRegistry.transition(
                project["project_id"],
                project,
                "run-new::best",
                "production",
            )

    assert len(persisted_project_states) == 2
    assert persisted_project_states[0]["current"]["best_model_id"] == "run-new::best"
    assert persisted_project_states[1] == project_before
    assert project == project_before
    assert json.loads(registry_path.read_text(encoding="utf-8")) == registry_before
