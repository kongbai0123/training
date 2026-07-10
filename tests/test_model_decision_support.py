import json
import unittest
from pathlib import Path
from unittest.mock import patch

from src.api.routes.models import list_project_model_catalog
from src.model_recommendation import rank_models_for_project
from src.model_system.catalog import ModelCatalog, normalize_task_family


ROOT = Path(__file__).resolve().parents[1]


class ModelDecisionMetadataTests(unittest.TestCase):
    def test_metadata_catalog_is_valid_and_enriches_builtin_models(self):
        payload = json.loads((ROOT / "data" / "model_decision_metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], 1)
        models = {item["model_id"]: item for item in ModelCatalog.list_all()}
        yolo = models["builtin.yolo26n-seg"]
        rnn = models["template.rnn.lstm-classifier"]
        self.assertEqual(yolo["benchmark"]["primary_metric"]["key"], "mask_map50_95")
        self.assertEqual(yolo["decision_profile"]["scale"], "nano")
        self.assertIn("zh-TW", rnn["decision_profile"]["summary"])
        self.assertEqual(normalize_task_family("semantic_segmentation"), "segmentation")

    def test_ranking_is_task_local_and_objective_aware(self):
        models = [
            {
                "model_id": "fast",
                "usable": True,
                "trainable": True,
                "hardware_fit": "ready",
                "decision_profile": {"scale": "nano"},
                "benchmark": {
                    "primary_metric": {"value": 35},
                    "latency": {"cpu_onnx_ms": 20},
                    "parameters_m": 2,
                },
            },
            {
                "model_id": "accurate",
                "usable": True,
                "trainable": True,
                "hardware_fit": "ready",
                "decision_profile": {"scale": "small"},
                "benchmark": {
                    "primary_metric": {"value": 50},
                    "latency": {"cpu_onnx_ms": 180},
                    "parameters_m": 15,
                },
            },
        ]
        project = {"task_type": "segmentation", "images": [{"filename": f"{i}.jpg"} for i in range(200)]}
        speed_ranked = rank_models_for_project(models, {}, project, "speed")
        accuracy_ranked = rank_models_for_project(models, {}, project, "accuracy")
        self.assertEqual(speed_ranked[0]["model_id"], "fast")
        self.assertEqual(accuracy_ranked[0]["model_id"], "accurate")

    def test_sample_count_accepts_legacy_filename_entries(self):
        ranked = rank_models_for_project(
            [{"model_id": "candidate", "usable": True, "trainable": True, "hardware_fit": "ready"}],
            {},
            {"task_type": "detection", "images": ["one.jpg", {"filename": "two.jpg"}, {"filename": "aug.jpg", "is_augmented": True}]},
        )
        self.assertEqual(ranked[0]["decision_context"]["sample_count"], 2)

    @patch("src.api.routes.models.get_system_capabilities")
    @patch("src.api.routes.models.ModelCatalog.list_trainable")
    @patch("src.api.routes.models.ProjectManager.get_project")
    def test_project_catalog_returns_decision_contract(self, get_project, list_trainable, capabilities):
        get_project.return_value = {"task_type": "segmentation", "images": []}
        list_trainable.return_value = [{
            "model_id": "candidate",
            "trainable": True,
            "usable": True,
            "installation_required": False,
            "decision_profile": {"scale": "nano"},
        }]
        capabilities.return_value = {
            "gpu": {"cuda_available": False, "devices": []},
            "memory": {},
            "disk": {},
        }
        response = list_project_model_catalog("project", architecture="cnn", usage="train", objective="balanced")
        self.assertEqual(response["objective"], "balanced")
        self.assertEqual(response["models"][0]["recommendation_rank"], 1)
        self.assertEqual(response["decision_summary"]["recommended"], ["candidate"])


if __name__ == "__main__":
    unittest.main()
