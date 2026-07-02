import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from src.model_system.catalog import ModelCatalog


class CustomPackageManifestContractTests(unittest.TestCase):
    def _project(self, project_dir: Path) -> dict:
        dataset = project_dir / "dataset"
        (dataset / "images" / "raw").mkdir(parents=True, exist_ok=True)
        return {
            "project_id": project_dir.name,
            "project_name": "custom",
            "dataset_path": dataset.as_posix(),
            "task_type": "semantic_segmentation",
            "layout": {"mode": "v3", "version": "v3"},
            "class_names": ["road"],
        }

    def test_manifest_yaml_package_validates_without_enabling_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._project(root / "proj_custom")
            package = root / "custom_model_package.zip"
            manifest_yaml = """
schema_version: 1
model:
  name: Custom Road Model
  architecture: cnn
  task_type: segmentation
  framework: pytorch
entrypoints:
  trainer: train.train
  predictor: predict.predict
input:
  type: image
  shape: [3, 640, 640]
  dtype: float32
output:
  type: segmentation_mask
  classes: [asphalt, cement, gravel]
  format: mask
metrics:
  required: [train/loss, val/loss]
  optional: [precision, recall, f1, miou]
security:
  allow_network: false
  allow_shell: false
  allow_write: false
"""
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("manifest.yaml", manifest_yaml)
                archive.writestr("train.py", "raise RuntimeError('must not execute')\n")
                archive.writestr("predict.py", "raise RuntimeError('must not execute')\n")

            result = ModelCatalog.import_custom_package(
                project=project,
                source_path=package,
                display_name="Custom Road Model",
                task_family="segmentation",
            )

            self.assertTrue(result["success"])
            self.assertTrue(result["validation"]["manifest_valid"])
            self.assertFalse(result["validation"]["execution_enabled"])
            self.assertEqual(result["validation"]["status"], "REGISTERED_DISABLED")
            manifest = result["validation"]["manifest"]
            self.assertEqual(manifest["model_name"], "Custom Road Model")
            self.assertEqual(manifest["runtime"]["entrypoint"], "train.train")
            self.assertEqual(manifest["runtime"]["entrypoint_file"], "train.py")
            self.assertTrue(Path(result["manifest_path"]).exists())
            self.assertTrue((Path(result["manifest_path"]).parent / "source_model_manifest.json").exists())
            self.assertFalse(result["model"]["trainable"])
            self.assertFalse(result["model"]["inference_supported"])

    def test_manifest_yaml_inside_single_wrapper_folder_validates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._project(root / "proj_custom")
            package = root / "wrapped_package.zip"
            manifest_yaml = """
schema_version: 1
model:
  name: Wrapped Road Model
  architecture: cnn
  task_type: segmentation
  framework: pytorch
entrypoints:
  trainer: train.train
input:
  type: image
  shape: [3, 640, 640]
output:
  type: segmentation_mask
  classes: [road]
capabilities:
  train: true
  infer: true
security:
  allow_network: false
  allow_shell: false
"""
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("wrapped/manifest.yaml", manifest_yaml)
                archive.writestr("wrapped/train.py", "raise RuntimeError('must not execute')\n")

            result = ModelCatalog.import_custom_package(
                project=project,
                source_path=package,
                display_name="Wrapped Road Model",
                task_family="segmentation",
            )

            self.assertTrue(result["success"])
            manifest = result["validation"]["manifest"]
            self.assertEqual(manifest["package_root"], "wrapped")
            self.assertEqual(manifest["runtime"]["entrypoint_file"], "wrapped/train.py")

    def test_legacy_model_manifest_json_still_validates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._project(root / "proj_custom")
            package = root / "legacy_package.zip"
            manifest = {
                "schema_version": "1.0",
                "model_id": "custom_road_seg_v1",
                "model_name": "Custom Road Segmentation",
                "model_type": "cnn",
                "task": "segmentation",
                "runtime": {"kind": "python_adapter", "entrypoint": "adapter.py"},
                "artifacts": {"source": ["adapter.py"]},
                "input_spec": {"type": "image", "shape": [1, 3, 640, 640], "dtype": "float32"},
                "output_spec": {"type": "segmentation_mask", "classes": ["road"], "format": "mask"},
                "capabilities": {"train": False, "infer": True, "evaluate": True},
                "security": {"requires_network": False, "writes_files": False, "requires_shell": False, "requires_gpu": False},
                "dependency_policy": {"install_allowed": False, "requirements_file": None},
            }
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("model_manifest.json", json.dumps(manifest))
                archive.writestr("adapter.py", "raise RuntimeError('must not execute')\n")

            result = ModelCatalog.import_custom_package(
                project=project,
                source_path=package,
                display_name="Legacy Package",
                task_family="segmentation",
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["validation"]["manifest"]["runtime"]["entrypoint_file"], "adapter.py")

    def test_dotted_entrypoint_mock_runner_checks_derived_file_without_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._project(root / "proj_custom")
            package = root / "custom_model_package.zip"
            manifest_yaml = """
schema_version: 1
model:
  name: Custom Road Model
  architecture: cnn
  task_type: segmentation
  framework: pytorch
entrypoints:
  trainer: train.train
input:
  type: image
  shape: [3, 640, 640]
output:
  type: segmentation_mask
  classes: [road]
security:
  allow_network: false
  allow_shell: false
"""
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("manifest.yaml", manifest_yaml)
                archive.writestr("train.py", "raise RuntimeError('must not execute')\n")

            imported = ModelCatalog.import_custom_package(
                project=project,
                source_path=package,
                display_name="Custom Road Model",
                task_family="segmentation",
            )
            model_id = imported["model"]["model_id"]
            ModelCatalog.request_custom_package_dry_run(project, model_id)
            ModelCatalog.record_custom_package_dry_run_approval(project, model_id, decision="approve")
            result = ModelCatalog.run_custom_package_mock_dry_run(project, model_id)

            self.assertTrue(result["success"])
            checks = {item["name"]: item for item in result["dry_run"]["checks"]}
            self.assertTrue(checks["entrypoint_file_exists"]["passed"])
            self.assertFalse(result["dry_run"]["adapter_imported"])
            self.assertFalse(result["dry_run"]["user_code_executed"])

    def test_multiple_manifest_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._project(root / "proj_custom")
            package = root / "ambiguous_package.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("manifest.yaml", "schema_version: 1\n")
                archive.writestr("model_manifest.json", "{}")

            result = ModelCatalog.import_custom_package(
                project=project,
                source_path=package,
                display_name="Ambiguous Package",
                task_family="segmentation",
            )

            self.assertFalse(result["success"])
            self.assertTrue(any("multiple manifests" in error for error in result["validation"]["errors"]))


if __name__ == "__main__":
    unittest.main()
