import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from src.api.routes.models import router as models_router
from src.api.routes.tabular import _inference_service, router as tabular_router
from src.model_lifecycle_registry import ModelLifecycleRegistry
from src.model_registry import ModelRegistry
from src.project_layout import ProjectLayout
from src.project_manager import ProjectManager
from src.tabular_config import compute_tabular_config_hash, inspect_tabular_csv, validate_tabular_config
from src.tabular_xgboost_inference import TabularXGBoostInferenceService
from src.training.backends.tabular_xgboost_backend import TabularXGBoostBackend
from src.training.compare_service import CompareService
from src.training.export_service import ExportService, ExportableModelNotFound
from src.training.rnn.xgboost_trainer import XGBoostTrainingError, train_xgboost_from_dataset
from src.training.tabular.dataset import load_csv_tabular_dataset


class TabularBackendIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.projects_root = self.root / "projects"
        self.project_dir = self.projects_root / "proj_tabular"
        self.layout_data = {"version": "v3", "mode": "v3"}
        ProjectLayout(self.project_dir, {"layout": self.layout_data}).ensure_v3_tree()
        self.csv_path = self.project_dir / "dataset" / "tables" / "quality.csv"
        rows = ["temperature,pressure,target"]
        for index in range(60):
            temperature = "" if index == 5 else str(index + 1)
            label = "alarm" if index % 2 else "normal"
            rows.append(f"{temperature},{100 + index},{label}")
        self.csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

        self.project = {
            "project_id": "proj_tabular",
            "project_name": "Tabular integration",
            "dataset_path": (self.project_dir / "dataset").as_posix(),
            "layout": dict(self.layout_data),
            "layout_version": "v3",
            "task_type": "tabular_classification",
            "tabular_config": {
                "source_file": "dataset/tables/quality.csv",
                "feature_columns": ["temperature", "pressure"],
                "target_column": "target",
                "id_column": "",
                "split_column": "",
                "task_head": "classification",
                "seed": 11,
                "train_ratio": 0.70,
                "val_ratio": 0.15,
                "test_ratio": 0.15,
                "missing_strategy": "median",
                "feature_config_hash": "configured-hash",
            },
            "training_config": {},
            "training_runs": [],
            "current": {},
        }

    def tearDown(self):
        self.temporary.cleanup()

    def _train(self, run_id: str, learning_rate: float) -> Path:
        task_head = str(self.project.get("tabular_config", {}).get("task_head") or "classification")
        self.project["training_config"] = {
            "run_id": run_id,
            "backend": "xgboost_tabular",
            "architecture": "tabular",
            "model": "xgboost_regressor" if task_head == "regression" else "xgboost_classifier",
            "epochs": 3,
            "lr0": 0.9,
            "learning_rate": learning_rate,
            "max_depth": 2,
            "subsample": 1.0,
            "colsample_bytree": 1.0,
            "seed": 11,
            "workers": 1,
        }
        backend = TabularXGBoostBackend()
        with patch(
            "src.training.backends.tabular_xgboost_backend.ProjectManager.save_project",
            return_value=True,
        ):
            backend._run_training(self.project)
        run_dir = self.project_dir / "training" / "runs" / run_id
        summary = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "completed", summary.get("error"))
        return run_dir

    def test_regression_backend_uses_regression_metrics_and_inference_contract(self):
        rows = ["temperature,pressure,target"]
        rows.extend(
            f"{index},{100 + index},{(index * 0.75) + 2.0}" for index in range(1, 61)
        )
        self.csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        self.project["task_type"] = "tabular_regression"
        self.project["tabular_config"]["task_head"] = "regression"
        run_dir = self._train("run_tabular_regression", 0.05)

        summary = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
        metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["task_type"], "tabular_regression")
        self.assertEqual(summary["primary_metric_key"], "val/mae")
        self.assertIn("val/r2", metrics["best_metrics"])
        self.assertFalse((run_dir / "preprocess" / "label_encoder.json").exists())

        service = TabularXGBoostInferenceService.load_from_run(
            run_dir, trusted_root=self.project_dir
        )
        prediction = service.predict_one({"temperature": 12, "pressure": 112})
        self.assertIsInstance(prediction["prediction"], float)
        with patch("src.model_registry.PROJECTS_DIR", self.projects_root):
            best = [
                item for item in ModelRegistry.list_models(self.project)
                if item["weight_type"] == "best"
            ][0]
        self.assertEqual(best["task_type"], "tabular_regression")

    def test_complete_training_registry_lifecycle_inference_export_and_compare_chain(self):
        run_a = self._train("run_tabular_a", 0.05)
        run_b = self._train("run_tabular_b", 0.15)

        for run_dir in (run_a, run_b):
            for relative in (
                "weights/best.json",
                "preprocess/feature_schema.json",
                "preprocess/imputation.json",
                "feature_importance.json",
                "backend.json",
                "metric_schema.json",
                "artifact_manifest.json",
            ):
                self.assertTrue((run_dir / relative).is_file(), relative)
            manifest = json.loads((run_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["contract_version"], "2.0")
            self.assertEqual(manifest["lineage"]["dataset"]["source_file"], "dataset/tables/quality.csv")
            self.assertEqual(len(manifest["lineage"]["dataset"]["dataset_sha256"]), 64)
            self.assertEqual(manifest["lineage"]["model"]["model_id"].split("::")[-1], "best")
            importance = json.loads((run_dir / "feature_importance.json").read_text(encoding="utf-8"))
            self.assertEqual({item["feature"] for item in importance}, {"temperature", "pressure"})

        with patch("src.model_registry.PROJECTS_DIR", self.projects_root):
            models = ModelRegistry.list_models(self.project)
            self.assertEqual(len(models), 4)
            best_models = [item for item in models if item["weight_type"] == "best"]
            self.assertEqual({item["architecture"] for item in best_models}, {"tabular"})
            self.assertTrue(all(item["model_format"] == "json" for item in best_models))
            self.assertTrue(all(item["dataset_lineage"]["dataset_sha256"] for item in best_models))
            self.assertTrue(all("learning_rate" in item["training_parameters"] for item in best_models))
            self.assertTrue(all(item["evaluation"]["best_metrics"] for item in best_models))

            versions = ModelLifecycleRegistry.list_versions(self.project)
            self.assertEqual(versions["schema_version"], "2.0")
            self.assertEqual(len(versions["versions"]), 2)
            newest = versions["versions"][0]
            self.assertTrue(newest["dataset_lineage"]["dataset_sha256"])
            self.assertIn("learning_rate", newest["training_parameters"])
            self.assertIn("best_metrics", newest["evaluation"])

            with patch("src.model_lifecycle_registry.ProjectManager.save_project", return_value=True):
                ModelLifecycleRegistry.transition(
                    self.project["project_id"], self.project, newest["model_id"], "validated"
                )
                production = ModelLifecycleRegistry.transition(
                    self.project["project_id"], self.project, newest["model_id"], "production"
                )
            self.assertEqual(production["model"]["status"], "production")
            self.assertEqual(self.project["current"]["best_model_id"], newest["model_id"])

        service = TabularXGBoostInferenceService.load_from_run(
            run_b, trusted_root=self.project_dir
        )
        prediction = service.predict_one({"temperature": 15, "pressure": 114})
        self.assertIn(prediction["predicted_label"], {"alarm", "normal"})

        compared = CompareService.compare_runs(
            self.project, "tabular", ["run_tabular_a", "run_tabular_b"], "run_tabular_a"
        )
        self.assertEqual(compared["architecture"], "tabular")
        self.assertEqual(compared["task_family"], "classification")
        self.assertIn("learning_rate", compared["summary"]["config_diff"])
        self.assertTrue(all(run["artifacts"] for run in compared["selected_runs"]))

        with patch("src.training.export_service.ProjectManager.save_project", return_value=True):
            exported = ExportService.export_project_model(
                self.project["project_id"], self.project, run_id="run_tabular_b"
            )
        self.assertEqual(exported["export_type"], "tabular_model_package")
        package_path = Path(exported["package_path"])
        self.assertTrue(package_path.is_file())
        with zipfile.ZipFile(package_path) as archive:
            names = set(archive.namelist())
        self.assertIn("weights/best.json", names)
        self.assertIn("preprocess/imputation.json", names)
        self.assertIn("inference_contract.json", names)

    def test_config_inspection_matches_numeric_loader_and_validates_mvp_fields(self):
        mismatch = self.project_dir / "dataset" / "tables" / "mixed.csv"
        rows = ["id,feature,target"]
        rows.extend(f"{index},{index},A" for index in range(19))
        rows.append("20,not-numeric,B")
        mismatch.write_text("\n".join(rows) + "\n", encoding="utf-8")
        inspection = inspect_tabular_csv(mismatch)
        self.assertFalse(inspection["column_profiles"]["feature"]["is_numeric"])

        config = {
            "feature_columns": ["feature"],
            "target_column": "target",
            "id_column": "missing_id",
            "split_column": "target",
            "task_head": "classification",
            "missing_strategy": "mean",
            "train_ratio": 0.7,
            "val_ratio": 0.15,
            "test_ratio": 0.15,
        }
        validation = validate_tabular_config(config, inspection)
        self.assertFalse(validation["valid"])
        self.assertTrue(any("numeric" in message for message in validation["errors"]))
        self.assertTrue(any("ID column" in message for message in validation["errors"]))
        self.assertTrue(any("median" in message for message in validation["errors"]))

        malformed = self.project_dir / "dataset" / "tables" / "extra.csv"
        malformed.write_text("x,target\n1,A,extra\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "more values than the header"):
            inspect_tabular_csv(malformed)

    def test_training_requires_validation_rows_for_a_measurable_contract(self):
        tiny = self.project_dir / "dataset" / "tables" / "tiny.csv"
        tiny.write_text("x,target\n1,A\n2,B\n", encoding="utf-8")
        dataset = load_csv_tabular_dataset(tiny, target_column="target")
        self.assertEqual(dataset["tensors"]["val"]["x"].shape[0], 0)
        with self.assertRaisesRegex(XGBoostTrainingError, "validation row"):
            train_xgboost_from_dataset(
                dataset,
                self.project_dir / "training" / "runs" / "too_small",
                {"epochs": 1},
                architecture="tabular",
                task_prefix="tabular",
                backend_name="xgboost_tabular",
            )

    def test_backend_rejects_task_contract_mismatch_and_unsafe_parameters(self):
        backend = TabularXGBoostBackend()
        errors = backend.validate_readiness(self.project, {
            "run_id": "../foreign-run",
            "task_head": "regression",
            "epochs": 0,
            "learning_rate": 0,
            "max_depth": 100,
            "subsample": 1.5,
            "colsample_bytree": float("nan"),
            "seed": -1,
        })

        self.assertTrue(any("task_head" in message for message in errors))
        self.assertTrue(any("run_id" in message for message in errors))
        self.assertTrue(any("epochs" in message for message in errors))
        self.assertTrue(any("learning_rate" in message for message in errors))
        self.assertTrue(any("max_depth" in message for message in errors))
        self.assertTrue(any("subsample" in message for message in errors))
        self.assertTrue(any("colsample_bytree" in message for message in errors))
        self.assertTrue(any("seed" in message for message in errors))

    def test_zero_seed_and_zero_test_ratio_remain_part_of_the_training_contract(self):
        config = dict(self.project["tabular_config"])
        config.update({"seed": 0, "train_ratio": 0.8, "val_ratio": 0.2, "test_ratio": 0.0})
        zero_hash = compute_tabular_config_hash(config)
        changed_seed = compute_tabular_config_hash({**config, "seed": 42})
        changed_ratio = compute_tabular_config_hash(
            {**config, "train_ratio": 0.7, "val_ratio": 0.15, "test_ratio": 0.15}
        )
        self.assertNotEqual(zero_hash, changed_seed)
        self.assertNotEqual(zero_hash, changed_ratio)

        self.project["tabular_config"] = {**config, "feature_config_hash": zero_hash}
        run_dir = self._train("run_zero_seed", 0.05)
        snapshot = json.loads((run_dir / "dataset_snapshot.json").read_text(encoding="utf-8"))
        self.assertEqual(snapshot["seed"], 0)
        self.assertEqual(snapshot["split_counts"]["test"], 0)

    def test_explicit_export_rejects_failed_missing_or_foreign_runs(self):
        failed_dir = self.project_dir / "training" / "runs" / "run_failed"
        (failed_dir / "weights").mkdir(parents=True)
        (failed_dir / "weights" / "best.json").write_text("{}", encoding="utf-8")
        (failed_dir / "backend.json").write_text(
            json.dumps({"architecture": "tabular", "status": "failed"}), encoding="utf-8"
        )
        (failed_dir / "run_summary.json").write_text(
            json.dumps({"status": "failed"}), encoding="utf-8"
        )
        with patch("src.model_registry.PROJECTS_DIR", self.projects_root):
            self.assertEqual(ModelRegistry.list_models(self.project), [])
        with self.assertRaisesRegex(ExportableModelNotFound, "completed Tabular run"):
            ExportService.export_project_model(
                self.project["project_id"], self.project, run_id="run_failed"
            )
        with self.assertRaisesRegex(ExportableModelNotFound, "does not belong"):
            ExportService.export_project_model(
                self.project["project_id"],
                self.project,
                model_id="another_project::run_failed::best",
            )
        with self.assertRaisesRegex(ExportableModelNotFound, "do not match"):
            ExportService.export_project_model(
                self.project["project_id"],
                self.project,
                run_id="run_failed",
                model_id=f"{self.project['project_id']}::another_run::best",
            )
        self.project["training_runs"] = [
            {"run_id": "run_failed", "status": "failed", "architecture": "tabular"}
        ]
        with self.assertRaisesRegex(ValueError, "completed Tabular run"):
            _inference_service(self.project, "run_failed", None)

    def test_project_summary_and_api_contract_include_tabular_artifacts(self):
        weights = self.project_dir / "training" / "runs" / "run_one" / "weights"
        weights.mkdir(parents=True)
        (weights / "best.json").write_text("{}", encoding="utf-8")
        (weights / "last.json").write_text("{}", encoding="utf-8")
        summary = ProjectManager.build_project_file_summary(self.project_dir, self.project)
        self.assertEqual(summary["tabular_csv_files"], 1)
        self.assertEqual(summary["best_weights"], 1)
        self.assertEqual(summary["last_weights"], 1)

        tabular_paths = {route.path for route in tabular_router.routes}
        model_paths = {route.path for route in models_router.routes}
        self.assertIn("/api/projects/{project_id}/tabular/workspace", tabular_paths)
        self.assertIn("/api/projects/{project_id}/tabular/inference/row", tabular_paths)
        self.assertIn("/api/projects/{project_id}/models/versions", model_paths)
        self.assertIn("/api/projects/{project_id}/models/{model_id:path}/lifecycle", model_paths)


if __name__ == "__main__":
    unittest.main()
