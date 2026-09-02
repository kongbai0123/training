import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.project_manager import ProjectManager


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("task_type", "backend"),
    [
        ("semantic_segmentation", "ultralytics_yolo"),
        ("sequence_regression", "sklearn_xgboost"),
        ("tabular_classification", "xgboost_tabular"),
    ],
)
def test_legacy_project_load_preserves_identifiers_runs_and_unknown_fields(task_type, backend):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        project_id = f"legacy_{task_type}"
        project_dir = root / project_id
        project_dir.mkdir()
        original = {
            "project_id": project_id,
            "project_name": "Legacy",
            "task_type": task_type,
            "dataset_path": (project_dir / "dataset").as_posix(),
            "training_config": {"backend": backend, "model": "kept-model"},
            "training_runs": [{"run_id": "kept-run", "backend": backend}],
            "custom_extension": {"keep": True},
        }
        (project_dir / "project.json").write_text(json.dumps(original), encoding="utf-8")

        with patch("src.project_manager.PROJECTS_DIR", root):
            loaded = ProjectManager.get_project(project_id)

        saved = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
        assert loaded["task_type"] == task_type
        assert saved["training_config"]["backend"] == backend
        assert saved["training_runs"] == original["training_runs"]
        assert saved["custom_extension"] == original["custom_extension"]


def test_page_aliases_are_canonicalized_before_workspace_isolation():
    router = (ROOT / "static" / "core" / "router.js").read_text(encoding="utf-8")
    modes = (ROOT / "static" / "pages" / "training_modes.js").read_text(encoding="utf-8")

    for old_page, current_page in {
        '"cnn-training"': '"training"',
        '"rnn-training"': '"training"',
        '"tabular-model"': '"tabular"',
        'compare': '"model-compare"',
        '"labelme-manager"': '"labelme"',
    }.items():
        assert f"{old_page}: {current_page}" in router
    assert 'return KNOWN_PAGES.has(canonical) ? canonical : "dashboard"' in router
    assert "const page = canonicalizePageId(requestedPage);" in modes


def test_compatibility_document_defines_non_destructive_rollback_contract():
    document = (ROOT / "docs" / "WORKSPACE_COMPATIBILITY.md").read_text(encoding="utf-8")

    assert "不會自動更換 `task_type`" in document
    assert "不得使用已撤銷的 `0.2.0 runtime-r1` 增量包" in document
    assert "不需要批次反向遷移專案" in document
