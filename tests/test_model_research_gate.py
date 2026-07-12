import json
from pathlib import Path
from unittest.mock import patch

from src.api.routes.models import list_project_model_catalog
from src.model_system.catalog import ModelCatalog
from src.model_system.research_gate import evaluate_research_candidates


ROOT = Path(__file__).resolve().parents[1]


def test_research_registry_is_default_deny():
    payload = json.loads((ROOT / "data" / "model_research_registry.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["candidates"]
    assert all(candidate["execution_enabled"] is False for candidate in payload["candidates"])
    assert all(candidate["acceptance_gates"] for candidate in payload["candidates"])


def test_rf_detr_gate_reports_windows_and_package_blockers():
    result = evaluate_research_candidates()
    rf_detr = next(item for item in result["candidates"] if item["candidate_id"] == "rf-detr")
    assert rf_detr["runtime_evaluation"]["execution_enabled"] is False
    assert rf_detr["runtime_evaluation"]["blockers"]


def test_rf_detr_profiles_are_visible_but_not_trainable():
    models = {item["model_id"]: item for item in ModelCatalog.list_all(architecture="cnn")}
    rf_detr = models["research.rfdetr-n-det"]
    assert rf_detr["status"] == "blocked_windows_validation"
    assert rf_detr["trainable"] is False
    assert rf_detr["benchmark"]["primary_metric"]["value"] == 48.4


@patch("src.api.routes.models.get_system_capabilities")
@patch("src.api.routes.models.ProjectManager.get_project")
def test_guide_catalog_includes_research_models_for_matching_task(get_project, capabilities):
    get_project.return_value = {"project_id": "p", "task_type": "detection", "images": []}
    capabilities.return_value = {"gpu": {"cuda_available": False, "devices": []}, "memory": {}, "disk": {}}
    response = list_project_model_catalog("p", architecture="cnn", usage="guide")
    ids = {model["model_id"] for model in response["models"]}
    assert "research.rfdetr-n-det" in ids
    assert "research.rfdetr-n-seg" not in ids
