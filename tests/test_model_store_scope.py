import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.model_registry import ModelRegistry
from src.model_store import ModelStore
from src.training.readiness import validate_training_readiness


class ModelStoreScopeTests(unittest.TestCase):
    def _project(self, project_dir: Path) -> dict:
        return {
            "project_id": "project_a",
            "dataset_path": str(project_dir / "dataset"),
            "task_type": "detection",
            "class_names": ["object"],
            "images": [
                {"filename": "a.jpg", "split": "train", "annotations": [{"category": "object", "bbox": [0.5, 0.5, 0.2, 0.2]}]},
                {"filename": "b.jpg", "split": "val", "annotations": [{"category": "object", "bbox": [0.5, 0.5, 0.2, 0.2]}]},
            ],
        }

    def test_model_registry_keeps_project_run_weight_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            projects_root = root / "projects"
            models_dir = root / "models"
            project_dir = projects_root / "project_a"
            run_dir = project_dir / "training" / "runs" / "run_1"
            run_weights = run_dir / "weights"
            run_weights.mkdir(parents=True)
            run_weights.joinpath("best.pt").write_bytes(b"run-best")

            stored = models_dir / "project_a" / "run_1"
            stored.mkdir(parents=True)
            stored.joinpath("best.pt").write_bytes(b"store-best")

            project = {"project_id": "project_a", "dataset_path": str(project_dir / "dataset"), "task_type": "detection"}
            with patch("src.model_registry.PROJECTS_DIR", projects_root), patch("src.model_store.MODELS_DIR", models_dir):
                models = ModelRegistry.list_models(project)

            self.assertEqual(models[0]["model_id"], "project_a::run_1::best")
            self.assertEqual(models[0]["source"], "project_training_runs")
            self.assertIn("/projects/project_a/training/runs/run_1/weights/best.pt", models[0]["internal_weight_path"].replace("\\", "/"))

    def test_custom_training_weight_must_be_under_models_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            models_dir = root / "models"
            outside = root / "outside.pt"
            outside.write_bytes(b"weight")
            project = self._project(root / "project_a")

            with patch("src.model_store.MODELS_DIR", models_dir):
                errors = validate_training_readiness(project, {"model": outside.as_posix()})

            self.assertTrue(any("models directory" in error for error in errors))

    def test_training_weight_filename_resolves_from_models_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            models_dir = root / "models"
            models_dir.mkdir()
            models_dir.joinpath("custom.pt").write_bytes(b"weight")

            with patch("src.model_store.MODELS_DIR", models_dir):
                resolved = ModelStore.resolve_training_model("custom.pt")

            self.assertEqual(Path(resolved), models_dir / "custom.pt")

    def test_builtin_yolo_name_is_not_treated_as_unsafe_local_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            models_dir = Path(temp_dir) / "models"

            with patch("src.model_store.MODELS_DIR", models_dir):
                resolved = ModelStore.resolve_training_model("yolov8s-seg.pt")

            self.assertEqual(resolved, "yolov8s-seg.pt")


if __name__ == "__main__":
    unittest.main()
