import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.inference_engine import InferenceEngine
from src.trainer import YOLOTrainer
from src.training.backends.rtdetr_backend import RTDETRBackend
from src.training.dispatcher import TrainerDispatcher
from src.training.export_service import ExportService
from src.training.run_manager import RunManager


ROOT = Path(__file__).resolve().parents[1]


class RTDETRBackendTests(unittest.TestCase):
    def test_catalog_exposes_official_rtdetr_models(self):
        catalog = json.loads((ROOT / "data" / "builtin_model_catalog.json").read_text(encoding="utf-8"))
        models = {item["model_id"]: item for item in catalog}
        for model_id in ("builtin.rtdetr-l-det", "builtin.rtdetr-x-det"):
            self.assertEqual(models[model_id]["backend"], "ultralytics_rtdetr")
            self.assertTrue(models[model_id]["trainable"])
            self.assertEqual(len(models[model_id]["sha256"]), 64)

    def test_dispatcher_resolves_rtdetr_backend(self):
        backend = TrainerDispatcher.resolve_backend(config={"backend": "ultralytics_rtdetr"})
        self.assertIsInstance(backend, RTDETRBackend)

    def test_rtdetr_rejects_segmentation_projects(self):
        backend = RTDETRBackend()
        with patch.object(backend, "prepare_dataset"):
            blockers = backend.validate_readiness(
                {"task_type": "segmentation"},
                {"backend": "ultralytics_rtdetr"},
            )
        self.assertTrue(any("object detection" in blocker for blocker in blockers))

    @patch("src.trainer.RTDETR")
    def test_training_loader_uses_rtdetr_class(self, rtdetr):
        YOLOTrainer._load_training_model("rtdetr-l.pt", "ultralytics_rtdetr")
        rtdetr.assert_called_once_with("rtdetr-l.pt")

    @patch("src.inference_engine.RTDETR")
    def test_inference_loader_uses_rtdetr_class(self, rtdetr):
        InferenceEngine._model_cache.clear()
        with tempfile.TemporaryDirectory() as tmp:
            weight = Path(tmp) / "best.pt"
            weight.write_bytes(b"weight")
            InferenceEngine._get_model(str(weight), "ultralytics_rtdetr")
        rtdetr.assert_called_once()

    def test_run_contract_records_rtdetr_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run_rtdetr"
            RunManager.finalize_run(run_dir, "detection", "failed", "test", backend="ultralytics_rtdetr")
            contract = json.loads((run_dir / "backend.json").read_text(encoding="utf-8"))
            self.assertEqual(contract["backend"], "ultralytics_rtdetr")

    def test_export_backend_resolves_from_run_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            run_dir = project_dir / "training" / "runs" / "run_rtdetr"
            run_dir.mkdir(parents=True)
            (run_dir / "backend.json").write_text('{"backend":"ultralytics_rtdetr"}', encoding="utf-8")
            project = {"project_id": "project", "dataset_path": str(project_dir / "dataset")}
            self.assertEqual(
                ExportService._resolve_cnn_backend(project, "run_rtdetr", run_dir / "weights" / "best.pt"),
                "ultralytics_rtdetr",
            )


if __name__ == "__main__":
    unittest.main()
