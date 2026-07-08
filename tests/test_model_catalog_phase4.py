import tempfile
import unittest
import zipfile
import json
from pathlib import Path
from unittest.mock import patch

from src.model_store import ModelStore
from src.model_system.catalog import ModelCatalog
from src.model_system.sandbox_policy import (
    build_p2_isolated_dry_run_policy,
    build_p3_dependency_environment_check,
    build_p4_process_runner_enforcement,
    build_p5_registry_enablement_policy,
    build_p6_limited_integration_contract,
)


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

    def test_rnn_catalog_exposes_trainable_rnn_and_planned_xgboost_templates(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "proj_rnn"
            project = self._project(project_dir, task_type="sequence_classification")

            all_models = ModelCatalog.list_all(project=project, architecture="rnn")
            trainable = ModelCatalog.list_trainable(
                project=project,
                task_family="sequence_classification",
                architecture="rnn",
            )

            self.assertTrue(any(item["model_id"] == "template.rnn.lstm-classifier" for item in trainable))
            self.assertTrue(any(item["selector_value"] == "gru" for item in trainable))
            self.assertTrue(any(item["selector_value"] == "bilstm" for item in trainable))
            xgboost = next(item for item in all_models if item["model_id"] == "template.xgboost.classifier")
            self.assertEqual(xgboost["backend"], "sklearn_xgboost")
            self.assertTrue(xgboost["trainable"])
            self.assertTrue(xgboost["training_enabled"])
            fastrnn = next(item for item in all_models if item["model_id"] == "template.rnn.fastrnn-classifier")
            self.assertEqual(fastrnn["backend"], "pytorch_fastrnn")
            self.assertFalse(fastrnn["trainable"])
            self.assertFalse(fastrnn["training_enabled"])
            isolation_forest = next(item for item in all_models if item["model_id"] == "template.isolation_forest.classifier")
            self.assertEqual(isolation_forest["backend"], "sklearn_isolation_forest")
            self.assertFalse(isolation_forest["trainable"])
            self.assertFalse(isolation_forest["training_enabled"])

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

    def test_imported_yolo_pt_is_trainable_and_resolvable_for_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "projects" / "proj_a"
            project = self._project(project_dir)
            source = root / "custom_seg.pt"
            source.write_bytes(b"fake-weight")

            result = ModelCatalog.import_yolo_pt(
                project=project,
                source_path=source,
                display_name="Custom Trainable YOLO",
                task_family="segmentation",
            )

            self.assertTrue(result["success"])
            imported = result["model"]
            trainable = ModelCatalog.list_trainable(project=project, task_family="segmentation", architecture="cnn")
            selected = next((item for item in trainable if item["model_id"] == imported["model_id"]), None)

            self.assertIsNotNone(selected)
            self.assertTrue(selected["trainable"])
            self.assertEqual(selected["source"], "user_import")
            self.assertTrue(selected["training_value"].endswith(".pt"))
            with patch("src.model_store.PROJECTS_DIR", root / "projects"):
                resolved = ModelStore.resolve_training_model(selected["training_value"])
            self.assertEqual(Path(resolved), Path(selected["training_value"]))

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

    def test_project_trained_catalog_references_deployable_best_only(self):
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
            self.assertNotIn("trained.run_1.last", trained_ids)

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

    def test_import_custom_package_validates_manifest_without_enabling_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "proj_custom"
            project = self._project(project_dir)
            package = root / "custom_package.zip"
            manifest = {
                "schema_version": "1.0",
                "model_id": "custom_road_seg_v1",
                "model_name": "Custom Road Segmentation",
                "model_type": "cnn",
                "task": "segmentation",
                "runtime": {"kind": "python_adapter", "entrypoint": "adapter.py"},
                "artifacts": {"weights": ["weights/model.onnx"], "source": ["adapter.py"]},
                "input_spec": {"type": "image", "shape": [1, 3, 640, 640], "dtype": "float32"},
                "output_spec": {"type": "segmentation_mask", "classes": ["road"], "format": "mask"},
                "capabilities": {"train": False, "infer": True, "evaluate": True},
                "security": {"requires_network": False, "writes_files": False, "requires_shell": False, "requires_gpu": False},
                "dependency_policy": {"install_allowed": False, "requirements_file": None},
            }
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("model_manifest.json", json.dumps(manifest))
                archive.writestr("adapter.py", "raise RuntimeError('must not execute')\n")
                archive.writestr("weights/model.onnx", "fake-onnx")

            result = ModelCatalog.import_custom_package(
                project=project,
                source_path=package,
                display_name="Custom Package",
                task_family="segmentation",
            )

            self.assertTrue(result["success"])
            self.assertTrue(result["validation"]["manifest_valid"])
            self.assertFalse(result["validation"]["execution_enabled"])
            self.assertEqual(result["validation"]["status"], "REGISTERED_DISABLED")
            self.assertTrue(Path(result["validation_report_path"]).exists())
            model = result["model"]
            self.assertEqual(model["format"], "custom_package")
            self.assertEqual(model["status"], "REGISTERED_DISABLED")
            self.assertFalse(model["trainable"])
            self.assertFalse(model["inference_supported"])
            self.assertIn("/models/imports/staging/", model["manifest_path"].replace("\\", "/"))

            trainable = ModelCatalog.list_trainable(project=project, task_family="segmentation", architecture="custom")
            inference = ModelCatalog.list_inference_supported(project=project, task_family="segmentation", architecture="custom")
            all_models = ModelCatalog.list_all(project=project, architecture="custom")
            self.assertFalse(any(item["model_id"] == model["model_id"] for item in trainable))
            self.assertFalse(any(item["model_id"] == model["model_id"] for item in inference))
            self.assertTrue(any(item["model_id"] == model["model_id"] for item in all_models))

    def test_import_custom_package_rejects_zip_slip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "proj_custom"
            project = self._project(project_dir)
            package = root / "unsafe_package.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("../../evil.txt", "bad")

            result = ModelCatalog.import_custom_package(
                project=project,
                source_path=package,
                display_name="Unsafe Package",
                task_family="segmentation",
            )

            self.assertFalse(result["success"])
            self.assertEqual(result["validation"]["status"], "REJECTED")
            self.assertTrue(any("Unsafe package path" in error for error in result["validation"]["errors"]))
            self.assertFalse((project_dir.parent / "evil.txt").exists())

    def test_import_custom_package_rejects_missing_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "proj_custom"
            project = self._project(project_dir)
            package = root / "missing_manifest.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("adapter.py", "print('not executed')\n")

            result = ModelCatalog.import_custom_package(
                project=project,
                source_path=package,
                display_name="Missing Manifest",
                task_family="segmentation",
            )

            self.assertFalse(result["success"])
            self.assertEqual(result["validation"]["status"], "REJECTED")
            self.assertTrue(any("model_manifest.json" in error for error in result["validation"]["errors"]))

    def test_custom_package_dry_run_request_requires_approval_without_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "proj_custom"
            project = self._project(project_dir)
            package = root / "custom_package.zip"
            manifest = {
                "schema_version": "1.0",
                "model_id": "custom_road_seg_v1",
                "model_name": "Custom Road Segmentation",
                "model_type": "cnn",
                "task": "segmentation",
                "runtime": {"kind": "python_adapter", "entrypoint": "adapter.py"},
                "artifacts": {"weights": ["weights/model.onnx"], "source": ["adapter.py"]},
                "input_spec": {"type": "image", "shape": [1, 3, 640, 640], "dtype": "float32"},
                "output_spec": {"type": "segmentation_mask", "classes": ["road"], "format": "mask"},
                "capabilities": {"train": False, "infer": True, "evaluate": True},
                "security": {"requires_network": True, "writes_files": False, "requires_shell": False, "requires_gpu": False},
                "dependency_policy": {"install_allowed": False, "requirements_file": None},
            }
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("model_manifest.json", json.dumps(manifest))
                archive.writestr("adapter.py", "raise RuntimeError('must not execute')\n")

            imported = ModelCatalog.import_custom_package(
                project=project,
                source_path=package,
                display_name="Custom Package",
                task_family="segmentation",
            )
            model_id = imported["model"]["model_id"]

            result = ModelCatalog.request_custom_package_dry_run(project, model_id)

            self.assertTrue(result["success"])
            dry_run = result["dry_run"]
            self.assertEqual(dry_run["status"], "APPROVAL_REQUIRED")
            self.assertFalse(dry_run["execution_enabled"])
            self.assertFalse(dry_run["adapter_imported"])
            self.assertFalse(dry_run["dry_run_executed"])
            self.assertTrue(dry_run["permission_gate"]["approval_required"])
            requested_names = {item["name"] for item in dry_run["permission_gate"]["requested_permissions"]}
            self.assertIn("python_adapter_execution", requested_names)
            self.assertIn("network", requested_names)
            self.assertTrue(Path(result["dry_run_report_path"]).exists())

    def test_custom_package_approval_records_decision_but_keeps_execution_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "proj_custom"
            project = self._project(project_dir)
            package = root / "custom_package.zip"
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

            imported = ModelCatalog.import_custom_package(
                project=project,
                source_path=package,
                display_name="Custom Package",
                task_family="segmentation",
            )
            model_id = imported["model"]["model_id"]
            ModelCatalog.request_custom_package_dry_run(project, model_id)

            result = ModelCatalog.record_custom_package_dry_run_approval(
                project,
                model_id,
                decision="approve",
                approved_by="tester",
                note="unit test",
            )

            self.assertTrue(result["success"])
            approval = result["approval"]
            self.assertEqual(approval["status"], "APPROVED_EXECUTION_DISABLED")
            self.assertEqual(approval["decision"], "approve")
            self.assertFalse(approval["execution_enabled"])
            self.assertFalse(approval["adapter_imported"])
            self.assertFalse(approval["dry_run_executed"])
            self.assertEqual(approval["next_allowed_action"], "sandbox_runner_required")

    def test_custom_package_mock_dry_run_requires_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "proj_custom"
            project = self._project(project_dir)
            package = root / "custom_package.zip"
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

            imported = ModelCatalog.import_custom_package(
                project=project,
                source_path=package,
                display_name="Custom Package",
                task_family="segmentation",
            )

            result = ModelCatalog.run_custom_package_mock_dry_run(project, imported["model"]["model_id"])

            self.assertFalse(result["success"])
            dry_run = result["dry_run"]
            self.assertEqual(dry_run["status"], "BLOCKED_APPROVAL_REQUIRED")
            self.assertFalse(dry_run["execution_enabled"])
            self.assertFalse(dry_run["adapter_imported"])
            self.assertFalse(dry_run["user_code_executed"])

    def test_custom_package_mock_dry_run_completed_without_executing_adapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "proj_custom"
            project = self._project(project_dir)
            package = root / "custom_package.zip"
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

            imported = ModelCatalog.import_custom_package(
                project=project,
                source_path=package,
                display_name="Custom Package",
                task_family="segmentation",
            )
            model_id = imported["model"]["model_id"]
            ModelCatalog.request_custom_package_dry_run(project, model_id)
            ModelCatalog.record_custom_package_dry_run_approval(project, model_id, decision="approve")

            result = ModelCatalog.run_custom_package_mock_dry_run(project, model_id)

            self.assertTrue(result["success"])
            dry_run = result["dry_run"]
            self.assertEqual(dry_run["status"], "MOCK_DRY_RUN_COMPLETED")
            self.assertEqual(dry_run["execution_mode"], "mock")
            self.assertFalse(dry_run["execution_enabled"])
            self.assertFalse(dry_run["adapter_imported"])
            self.assertFalse(dry_run["dry_run_executed"])
            self.assertFalse(dry_run["user_code_executed"])
            self.assertTrue(Path(result["mock_dry_run_report_path"]).exists())
            checks = {item["name"]: item for item in dry_run["checks"]}
            self.assertTrue(checks["entrypoint_file_exists"]["passed"])
            self.assertTrue(checks["user_code_not_executed"]["passed"])

    def test_custom_package_sandbox_plan_requires_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "proj_custom"
            project = self._project(project_dir)
            package = root / "custom_package.zip"
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

            imported = ModelCatalog.import_custom_package(
                project=project,
                source_path=package,
                display_name="Custom Package",
                task_family="segmentation",
            )

            result = ModelCatalog.build_custom_package_sandbox_plan(project, imported["model"]["model_id"])

            self.assertFalse(result["success"])
            plan = result["plan"]
            self.assertEqual(plan["status"], "BLOCKED_APPROVAL_REQUIRED")
            self.assertFalse(plan["execution_enabled"])
            self.assertFalse(plan["adapter_imported"])
            self.assertFalse(plan["user_code_executed"])

    def test_custom_package_sandbox_plan_ready_after_approval_without_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "proj_custom"
            project = self._project(project_dir)
            package = root / "custom_package.zip"
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

            imported = ModelCatalog.import_custom_package(
                project=project,
                source_path=package,
                display_name="Custom Package",
                task_family="segmentation",
            )
            model_id = imported["model"]["model_id"]
            ModelCatalog.request_custom_package_dry_run(project, model_id)
            ModelCatalog.record_custom_package_dry_run_approval(project, model_id, decision="approve")

            result = ModelCatalog.build_custom_package_sandbox_plan(project, model_id)

            self.assertTrue(result["success"])
            plan = result["plan"]
            self.assertEqual(plan["status"], "SANDBOX_PLAN_READY")
            self.assertFalse(plan["execution_enabled"])
            self.assertFalse(plan["adapter_imported"])
            self.assertFalse(plan["dry_run_executed"])
            self.assertFalse(plan["user_code_executed"])
            self.assertEqual(plan["sandbox_policy"]["write_scope"], "staging_only")
            self.assertEqual(plan["p2_isolated_runner_policy"]["status"], "P2_POLICY_DESIGNED")
            self.assertFalse(plan["p2_isolated_runner_policy"]["execution_enabled"])
            self.assertFalse(plan["p2_isolated_runner_policy"]["allowed"]["adapter_import"])
            self.assertIn("separate_process", plan["p2_isolated_runner_policy"]["required_controls"])
            self.assertTrue(Path(result["sandbox_plan_path"]).exists())

    def test_custom_package_sandbox_audit_records_request_approval_plan_and_mock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "proj_custom"
            project = self._project(project_dir)
            package = root / "custom_package.zip"
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

            imported = ModelCatalog.import_custom_package(
                project=project,
                source_path=package,
                display_name="Custom Package",
                task_family="segmentation",
            )
            model_id = imported["model"]["model_id"]
            ModelCatalog.request_custom_package_dry_run(project, model_id)
            ModelCatalog.record_custom_package_dry_run_approval(project, model_id, decision="approve")
            ModelCatalog.build_custom_package_sandbox_plan(project, model_id)
            ModelCatalog.run_custom_package_mock_dry_run(project, model_id)

            result = ModelCatalog.get_custom_package_sandbox_audit(project, model_id)

            self.assertTrue(result["success"])
            events = [item["event"] for item in result["audit"]]
            self.assertIn("dry_run_permission_requested", events)
            self.assertIn("dry_run_permission_approve", events)
            self.assertIn("sandbox_plan_created", events)
            self.assertIn("mock_dry_run_contract_checked", events)
            self.assertTrue(Path(result["audit_log_path"]).exists())
            self.assertTrue(all(item["execution_enabled"] is False for item in result["audit"]))
            self.assertTrue(all(item["user_code_executed"] is False for item in result["audit"]))

    def test_p2_sandbox_policy_is_design_only_and_default_deny(self):
        manifest = {
            "runtime": {"kind": "python_adapter", "entrypoint": "adapter.py"},
            "security": {
                "requires_network": True,
                "requires_shell": True,
                "requires_gpu": True,
                "writes_files": True,
            },
            "dependency_policy": {"install_allowed": True},
        }

        policy = build_p2_isolated_dry_run_policy(manifest)

        self.assertEqual(policy["status"], "P2_POLICY_DESIGNED")
        self.assertTrue(policy["runtime_supported"])
        self.assertFalse(policy["execution_enabled"])
        self.assertTrue(all(value is False for value in policy["allowed"].values()))
        self.assertIn("separate_process", policy["required_controls"])
        self.assertIn("stdout_json_contract", policy["required_controls"])
        self.assertTrue(any("Network access is denied" in reason for reason in policy["blocked_reasons"]))
        self.assertTrue(any("Dependency installation is denied" in reason for reason in policy["blocked_reasons"]))

    def test_p3_dependency_check_blocks_missing_lock_file_without_installing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = {
                "runtime": {"kind": "python_adapter", "entrypoint": "adapter.py"},
                "dependency_policy": {
                    "install_allowed": False,
                    "requirements_file": "requirements.txt",
                    "lock_file": "requirements.lock",
                    "offline_required": True,
                },
            }
            (root / "requirements.txt").write_text("numpy==1.0.0\n", encoding="utf-8")

            check = build_p3_dependency_environment_check(root, manifest)

            self.assertEqual(check["status"], "P3_DEPENDENCY_CHECK_BLOCKED")
            self.assertFalse(check["execution_enabled"])
            self.assertFalse(check["dependency_install_executed"])
            self.assertFalse(check["network_used"])
            checks = {item["name"]: item for item in check["checks"]}
            self.assertTrue(checks["requirements_file_exists"]["passed"])
            self.assertFalse(checks["lock_file_exists"]["passed"])

    def test_p3_and_p4_contracts_pass_with_lock_but_do_not_execute(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = {
                "runtime": {"kind": "python_adapter", "entrypoint": "adapter.py"},
                "dependency_policy": {
                    "install_allowed": False,
                    "requirements_file": "requirements.txt",
                    "lock_file": "requirements.lock",
                    "offline_required": True,
                },
            }
            (root / "requirements.txt").write_text("numpy==1.0.0\n", encoding="utf-8")
            (root / "requirements.lock").write_text("numpy==1.0.0 --hash=sha256:test\n", encoding="utf-8")

            p3_check = build_p3_dependency_environment_check(root, manifest)
            p4_contract = build_p4_process_runner_enforcement(manifest, p3_check)

            self.assertEqual(p3_check["status"], "P3_DEPENDENCY_CHECK_PASSED")
            self.assertEqual(p4_contract["status"], "P4_RUNNER_ENFORCEMENT_READY")
            self.assertFalse(p4_contract["execution_enabled"])
            self.assertFalse(p4_contract["process_spawned"])
            self.assertFalse(p4_contract["adapter_imported"])
            self.assertFalse(p4_contract["dry_run_executed"])
            self.assertFalse(p4_contract["user_code_executed"])
            self.assertTrue(p4_contract["controls"]["separate_process"])
            self.assertTrue(p4_contract["controls"]["network_disabled"])

    def test_sandbox_plan_embeds_p3_and_p4_contracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "proj_custom"
            project = self._project(project_dir)
            package = root / "custom_package.zip"
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
                "dependency_policy": {
                    "install_allowed": False,
                    "requirements_file": "requirements.txt",
                    "lock_file": "requirements.lock",
                    "offline_required": True,
                },
            }
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("model_manifest.json", json.dumps(manifest))
                archive.writestr("adapter.py", "raise RuntimeError('must not execute')\n")
                archive.writestr("requirements.txt", "numpy==1.0.0\n")
                archive.writestr("requirements.lock", "numpy==1.0.0 --hash=sha256:test\n")

            imported = ModelCatalog.import_custom_package(
                project=project,
                source_path=package,
                display_name="Custom Package",
                task_family="segmentation",
            )
            model_id = imported["model"]["model_id"]
            ModelCatalog.request_custom_package_dry_run(project, model_id)
            ModelCatalog.record_custom_package_dry_run_approval(project, model_id, decision="approve")

            result = ModelCatalog.build_custom_package_sandbox_plan(project, model_id)

            self.assertTrue(result["success"])
            self.assertEqual(result["plan"]["p3_dependency_environment_check"]["status"], "P3_DEPENDENCY_CHECK_PASSED")
            self.assertEqual(result["plan"]["p4_process_runner_enforcement"]["status"], "P4_RUNNER_ENFORCEMENT_READY")
            self.assertFalse(result["plan"]["p4_process_runner_enforcement"]["process_spawned"])
            self.assertFalse(result["plan"]["p4_process_runner_enforcement"]["user_code_executed"])

    def test_p5_enablement_blocks_mock_dry_run(self):
        model = {
            "model_id": "custom.package.test",
            "capabilities": {"train": True, "infer": True, "evaluate": True},
        }
        dry_run_report = {
            "status": "MOCK_DRY_RUN_COMPLETED",
            "adapter_imported": False,
            "dry_run_executed": False,
            "user_code_executed": False,
        }
        sandbox_plan = {
            "p3_dependency_environment_check": {"status": "P3_DEPENDENCY_CHECK_PASSED"},
            "p4_process_runner_enforcement": {"status": "P4_RUNNER_ENFORCEMENT_READY"},
        }

        policy = build_p5_registry_enablement_policy(model, dry_run_report, sandbox_plan)

        self.assertEqual(policy["status"], "P5_ENABLEMENT_BLOCKED")
        self.assertFalse(policy["execution_enabled"])
        self.assertFalse(policy["eligible_for_registry_enablement"])
        self.assertEqual(policy["allowed_registry_status"], "REGISTERED_DISABLED")
        self.assertFalse(policy["allowed_capabilities"]["train"])
        self.assertTrue(any("Mock dry-run is not sufficient" in reason for reason in policy["blocked_reasons"]))

    def test_p5_future_real_dry_run_can_be_review_ready_without_auto_enabling(self):
        model = {
            "model_id": "custom.package.test",
            "capabilities": {"train": True, "infer": True, "evaluate": False},
        }
        dry_run_report = {
            "status": "REAL_DRY_RUN_PASSED",
            "adapter_imported": True,
            "dry_run_executed": True,
            "user_code_executed": True,
        }
        sandbox_plan = {
            "p3_dependency_environment_check": {"status": "P3_DEPENDENCY_CHECK_PASSED"},
            "p4_process_runner_enforcement": {"status": "P4_RUNNER_ENFORCEMENT_READY"},
        }

        policy = build_p5_registry_enablement_policy(model, dry_run_report, sandbox_plan)

        self.assertEqual(policy["status"], "P5_ENABLEMENT_REVIEW_READY")
        self.assertFalse(policy["execution_enabled"])
        self.assertTrue(policy["eligible_for_registry_enablement"])
        self.assertEqual(policy["allowed_registry_status"], "READY_FOR_REVIEW")
        self.assertTrue(policy["allowed_capabilities"]["train"])
        self.assertTrue(policy["allowed_capabilities"]["infer"])
        self.assertFalse(policy["allowed_capabilities"]["evaluate"])

    def test_p6_blocks_selector_visibility_until_p5_review_ready(self):
        model = {"model_id": "custom.package.test"}
        enablement = {
            "status": "P5_ENABLEMENT_BLOCKED",
            "allowed_capabilities": {"train": True, "infer": True, "evaluate": True},
        }

        contract = build_p6_limited_integration_contract(model, enablement)

        self.assertEqual(contract["status"], "P6_LIMITED_INTEGRATION_BLOCKED")
        self.assertFalse(contract["execution_enabled"])
        self.assertFalse(contract["selector_visibility"]["training_selector"])
        self.assertFalse(contract["selector_visibility"]["inference_selector"])
        self.assertFalse(contract["selector_visibility"]["evaluation_selector"])

    def test_catalog_p5_p6_outputs_keep_custom_package_disabled_after_mock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "proj_custom"
            project = self._project(project_dir)
            package = root / "custom_package.zip"
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
                "capabilities": {"train": True, "infer": True, "evaluate": True},
                "security": {"requires_network": False, "writes_files": False, "requires_shell": False, "requires_gpu": False},
                "dependency_policy": {
                    "install_allowed": False,
                    "requirements_file": "requirements.txt",
                    "lock_file": "requirements.lock",
                    "offline_required": True,
                },
            }
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("model_manifest.json", json.dumps(manifest))
                archive.writestr("adapter.py", "raise RuntimeError('must not execute')\n")
                archive.writestr("requirements.txt", "numpy==1.0.0\n")
                archive.writestr("requirements.lock", "numpy==1.0.0 --hash=sha256:test\n")

            imported = ModelCatalog.import_custom_package(
                project=project,
                source_path=package,
                display_name="Custom Package",
                task_family="segmentation",
            )
            model_id = imported["model"]["model_id"]
            ModelCatalog.request_custom_package_dry_run(project, model_id)
            ModelCatalog.record_custom_package_dry_run_approval(project, model_id, decision="approve")
            ModelCatalog.build_custom_package_sandbox_plan(project, model_id)
            ModelCatalog.run_custom_package_mock_dry_run(project, model_id)

            enablement = ModelCatalog.evaluate_custom_package_enablement(project, model_id)
            integration = ModelCatalog.build_custom_package_integration_contract(project, model_id)

            self.assertTrue(enablement["success"])
            self.assertEqual(enablement["enablement"]["status"], "P5_ENABLEMENT_BLOCKED")
            self.assertFalse(enablement["enablement"]["eligible_for_registry_enablement"])
            self.assertTrue(Path(enablement["enablement_policy_path"]).exists())
            self.assertTrue(integration["success"])
            self.assertEqual(integration["integration"]["status"], "P6_LIMITED_INTEGRATION_BLOCKED")
            self.assertFalse(integration["integration"]["selector_visibility"]["training_selector"])
            self.assertFalse(integration["integration"]["selector_visibility"]["inference_selector"])
            self.assertTrue(Path(integration["integration_contract_path"]).exists())


if __name__ == "__main__":
    unittest.main()
