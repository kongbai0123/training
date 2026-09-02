import json
import threading
from pathlib import Path

import pytest

from src.path_security import validate_leaf_filename, validate_resource_id
from src.project_repository import ProjectRepository, ProjectRevisionConflict
from src.task_jobs import TaskJobManager


def _project(project_id="proj_safe"):
    return {"project_id": project_id, "revision": 0, "dataset_path": "dataset", "counter": 0}


def test_project_repository_serializes_parallel_mutations(tmp_path):
    repository = ProjectRepository(tmp_path)
    repository.write("proj_safe", _project())

    def increment():
        repository.mutate("proj_safe", lambda project: project.__setitem__("counter", project["counter"] + 1))

    threads = [threading.Thread(target=increment) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    saved = repository.read("proj_safe")
    assert saved["counter"] == 20
    assert saved["revision"] == 21


def test_project_repository_rejects_stale_revision_and_recovers_backup(tmp_path):
    repository = ProjectRepository(tmp_path)
    first = repository.write("proj_safe", _project())
    second, _ = repository.mutate("proj_safe", lambda project: project.__setitem__("counter", 1))
    with pytest.raises(ProjectRevisionConflict):
        repository.mutate("proj_safe", lambda project: None, expected_revision=first["revision"])

    project_file = tmp_path / "proj_safe" / "project.json"
    project_file.write_text("{damaged", encoding="utf-8")
    recovered = repository.read("proj_safe")
    assert recovered["recovery"]["code"] == "PROJECT_RECOVERED"
    assert recovered["revision"] == first["revision"]
    assert json.loads(project_file.read_text(encoding="utf-8"))["revision"] == first["revision"]


def test_task_journal_marks_active_work_interrupted(tmp_path):
    job_dir = tmp_path / "task_import_fixture"
    job_dir.mkdir(parents=True)
    job_dir.joinpath("job.json").write_text(json.dumps({
        "job_id": "task_import_fixture",
        "kind": "import",
        "title": "Import",
        "project_id": "proj_safe",
        "status": "running",
        "phase": "processing",
        "message": "Processing",
        "progress": 50,
        "history": [],
        "created_at": "2026-09-02T00:00:00+00:00",
        "updated_at": "2026-09-02T00:00:01+00:00",
    }), encoding="utf-8")

    manager = TaskJobManager(journal_dir=tmp_path)
    restored = manager.get("task_import_fixture")
    assert restored["status"] == "interrupted"
    assert restored["error_code"] == "APP_RESTARTED"
    assert restored["retryable"] is True
    assert manager.snapshot(active_only=True) == []


@pytest.mark.parametrize("value", ["..", ".", "CON", "bad/name", "bad\\name", "name.", " name"])
def test_resource_ids_reject_unsafe_values(value):
    with pytest.raises(ValueError):
        validate_resource_id(value)


@pytest.mark.parametrize("value", ["../x.png", "folder/x.png", "NUL.txt", "bad\x00.png", "name. "])
def test_leaf_filenames_reject_traversal_and_windows_names(value):
    with pytest.raises(ValueError):
        validate_leaf_filename(value, {".png"})


def test_personal_workflow_frontend_contracts_are_present():
    root = Path(__file__).resolve().parents[1]
    state = (root / "static" / "state.js").read_text(encoding="utf-8")
    lifecycle = (root / "static" / "core" / "project_lifecycle.js").read_text(encoding="utf-8")
    html = (root / "static" / "index.html").read_text(encoding="utf-8")
    css = (root / "static" / "styles" / "layout.css").read_text(encoding="utf-8")
    assert "deriveLabelMeState" in state and "appState.labelme.synced" not in state
    assert "projectScope.begin(projectId)" in lifecycle and "projectScope.assertCurrent(scope)" in lifecycle
    assert 'role="dialog"' in html and 'aria-modal="true"' in html
    assert "prefers-reduced-motion" in css and ":focus-visible" in css
    assert 'data-experience-mode="guided"' in css
