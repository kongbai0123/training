import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from src.model_store import ModelStore
from src.model_system.catalog import ModelCatalog


class ModelCatalogPhase4Tests(unittest.TestCase):
    def _project(self, project_dir: Path, task_type: str = "semantic_segmentation") -> dict:
        dataset = project_dir / "dataset"
        (dataset / "images" / "raw").mkdir(parents=True, exist_ok=True)
        return {
            "project_id": project_dir.name,
            "project_name": "test",
            "dataset_path": dataset.as_posix(),
            "task_type": task_type,
            "layout": {"mode": "v3", "version": "v3"},
            "class_names": ["road"],
        }

    def test_builtin_catalog_filters_trainable_segmentation_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "proj_a"
            project = self._project(project_dir)

            models = ModelCatalog.list_trainable(project=project, task_family=project["task_type"], architecture="cnn")

            self.assertTrue(any(item["model_id"] == "builtin.yolov8n-seg" for item in models))
            self.assertFalse(any(item["model_id"] == "builtin.yolov8n-det" for item in models))

    def test_import_yolo_pt_writes_project_manifest_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "proj_a"
            project = self._project(project_dir)
            source = root / "custom.pt"
            source.write_bytes(b"fake-weight")

            result = ModelCatalog.import_yolo_pt(
                project=project,
                source_path=source,
                display_name="Custom RoadSeg",
                task_family="segmentation",
            )

            self.assertTrue(result["success"])
            model = result["model"]
            self.assertEqual(model["source"], "user_import")
            self.assertEqual(model["task_family"], "segmentation")
            self.assertEqual(model["status"], "validated_basic")
            self.assertTrue(Path(model["manifest_path"]).exists())
            self.assertTrue(Path(model["weight_path"]).exists())
            self.assertIn("/models/imports/", model["weight_path"].replace("\\", "/"))

    def test_model_store_allows_project_import_weights(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects_root = root / "projects"
            weight = projects_root / "proj_a" / "models" / "imports" / "imported.yolo.test.1" / "best.pt"
            weight.parent.mkdir(parents=True)
            weight.write_bytes(b"fake-weight")

            with patch("src.model_store.PROJECTS_DIR", projects_root):
                resolved = ModelStore.resolve_training_model(weight.as_posix())

            self.assertEqual(Path(resolved), weight)

    def test_import_yolo_yaml_accepts_model_architecture_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "proj_a"
            project = self._project(project_dir)
            source = root / "custom.yaml"
            source.write_text("nc: 1\nbackbone: []\nhead: []\n", encoding="utf-8")

            result = ModelCatalog.import_yolo_yaml(
                project=project,
                source_path=source,
                display_name="Custom YAML",
                task_family="segmentation",
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["model"]["format"], "yaml")
            self.assertEqual(Path(result["model"]["weight_path"]).name, "model.yaml")

    def test_import_yolo_yaml_rejects_dataset_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "proj_a"
            project = self._project(project_dir)
            source = root / "data.yaml"
            source.write_text("train: images/train\nval: images/val\nnames: [road]\nnc: 1\n", encoding="utf-8")

            result = ModelCatalog.import_yolo_yaml(
                project=project,
                source_path=source,
                display_name="Dataset YAML",
                task_family="segmentation",
            )

            self.assertFalse(result["success"])
            self.assertTrue(any("dataset YAML" in error for error in result["validation"]["errors"]))

    def test_project_trained_catalog_references_best_and_last(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects_root = root / "projects"
            project_dir = projects_root / "proj_a"
            project = self._project(project_dir)
            run_weights = project_dir / "training" / "runs" / "run_1" / "weights"
            run_weights.mkdir(parents=True)
            run_weights.joinpath("best.pt").write_bytes(b"best")
            run_weights.joinpath("last.pt").write_bytes(b"last")
            run_weights.parent.joinpath("run_summary.json").write_text('{"task_type": "segmentation"}', encoding="utf-8")

            with patch("src.model_registry.PROJECTS_DIR", projects_root):
                models = ModelCatalog.list_trainable(project=project, task_family="segmentation", architecture="cnn")

            trained_ids = {item["model_id"] for item in models if item.get("source") == "project_trained"}
            self.assertIn("trained.run_1.best", trained_ids)
            self.assertIn("trained.run_1.last", trained_ids)

    def test_import_onnx_registers_inference_only_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "proj_a"
            project = self._project(project_dir)
            source = root / "road.onnx"
            source.write_bytes(b"fake-onnx")

            result = ModelCatalog.import_onnx(
                project=project,
                source_path=source,
                display_name="Road ONNX",
                task_family="segmentation",
            )

            self.assertTrue(result["success"])
            model = result["model"]
            self.assertEqual(model["backend"], "onnxruntime")
            self.assertEqual(model["format"], "onnx")
            self.assertFalse(model["trainable"])
            self.assertTrue(model["inference_supported"])
            self.assertTrue(Path(model["weight_path"]).exists())

            trainable = ModelCatalog.list_trainable(project=project, task_family="segmentation", architecture="cnn")
            inference = ModelCatalog.list_inference_supported(project=project, task_family="segmentation", architecture="cnn")
            self.assertFalse(any(item["model_id"] == model["model_id"] for item in trainable))
            self.assertTrue(any(item["model_id"] == model["model_id"] for item in inference))

    def test_import_rnn_package_registers_preview_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "proj_rnn"
            project = self._project(project_dir, task_type="sequence_classification")
            package = root / "rnn_package.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("model_manifest.json", '{"architecture":"rnn","backend":"pytorch_lstm"}')
                archive.writestr("model.pt", "fake-model")
                archive.writestr("feature_schema.json", '{"features":["a"],"target":"label"}')
                archive.writestr("normalization_stats.json", '{"method":"none"}')
                archive.writestr("sequence_config.json", '{"sequence_length":16,"stride":8}')
                archive.writestr("label_encoder.json", '{"classes":["normal"]}')

            result = ModelCatalog.import_rnn_package(
                project=project,
                source_path=package,
                display_name="RNN Package",
                task_family="sequence_classification",
            )

            self.assertTrue(result["success"])
            model = result["model"]
            self.assertEqual(model["architecture"], "rnn")
            self.assertEqual(model["backend"], "pytorch_lstm")
            self.assertEqual(model["format"], "rnn_package")
            self.assertFalse(model["trainable"])
            self.assertTrue(model["inference_supported"])
            self.assertTrue(Path(model["manifest_path"]).exists())
            self.assertTrue(Path(model["weight_path"]).exists())

    def test_import_rnn_package_rejects_missing_required_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "proj_rnn"
            project = self._project(project_dir, task_type="sequence_classification")
            package = root / "broken_rnn_package.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("model_manifest.json", '{"architecture":"rnn"}')
                archive.writestr("model.pt", "fake-model")

            result = ModelCatalog.import_rnn_package(
                project=project,
                source_path=package,
                display_name="Broken RNN Package",
                task_family="sequence_classification",
            )

            self.assertFalse(result["success"])
            self.assertTrue(any("feature_schema.json" in error for error in result["validation"]["errors"]))


if __name__ == "__main__":
    unittest.main()
