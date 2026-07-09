import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.dataset_quality_report import build_dataset_quality_report
from src.training.export_service import ExportService
from src.training.run_registry import ExperimentRunRegistry


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_rnn_run(root: Path, run_id: str = "run_rnn_lstm_001") -> Path:
    run_dir = root / "training" / "runs" / run_id
    run_dir.joinpath("weights").mkdir(parents=True, exist_ok=True)
    run_dir.joinpath("weights", "best.pt").write_bytes(b"fake model")
    write_json(run_dir / "metrics.json", {
        "architecture": "rnn",
        "backend": "pytorch_lstm",
        "task_type": "sequence_regression",
        "primary_metric": "val/mae",
        "best_metrics": {"val/mae": 0.12},
        "dataset_summary": {"sequence_length": 8},
        "residuals": [0.1, -0.2],
    })
    write_json(run_dir / "backend.json", {"architecture": "rnn", "backend": "pytorch_lstm"})
    write_json(run_dir / "run_summary.json", {"status": "completed", "task_type": "sequence_regression"})
    write_json(run_dir / "metric_schema.json", {"primary_metric": {"key": "val/mae"}})
    write_json(run_dir / "train_config.json", {"backend": "pytorch_lstm", "sequence_length": 8, "stride": 2, "horizon": 1})
    write_json(run_dir / "preprocess" / "feature_schema.json", {
        "feature_columns": ["pressure", "humidity"],
        "target_column": "target",
        "sequence_column": "",
        "time_column": "Date Time",
        "task_head": "regression",
    })
    write_json(run_dir / "preprocess" / "normalization_stats.json", {"mean": [1, 2], "std": [1, 1]})
    write_json(run_dir / "artifact_manifest.json", {
        "run_id": run_id,
        "artifacts": [
            {"name": "best.pt", "path": "weights/best.pt", "type": "model_weight", "size_bytes": 10},
            {"name": "feature_schema.json", "path": "preprocess/feature_schema.json", "type": "feature_schema", "size_bytes": 10},
            {"name": "metrics.json", "path": "metrics.json", "type": "metrics_json", "size_bytes": 10},
        ],
    })
    return run_dir


class RNNPlatformContractTests(unittest.TestCase):
    def test_quality_report_for_rnn_sequence_dataset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            csv_path = root / "sequences" / "sample.csv"
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            csv_path.write_text(
                "Date Time,pressure,humidity,target,split\n"
                "1,10,50,20,train\n"
                "2,11,,21,train\n"
                "3,12,52,22,val\n",
                encoding="utf-8",
            )
            project = {
                "project_id": "proj",
                "dataset_path": (root / "dataset").as_posix(),
                "task_type": "sequence_regression",
                "rnn_config": {
                    "feature_columns": ["pressure", "humidity"],
                    "target_column": "target",
                    "time_column": "Date Time",
                    "sequence_column": "",
                    "task_head": "regression",
                },
            }

            report = build_dataset_quality_report(project)

            self.assertEqual(report["architecture"], "rnn")
            self.assertEqual(report["kind"], "rnn_sequence")
            self.assertEqual(report["summary"]["row_count"], 3)
            self.assertIn("health_score", report)

    def test_run_registry_groups_rnn_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            run_id = "run_rnn_lstm_001"
            write_rnn_run(root, run_id)
            project = {
                "project_id": "proj",
                "dataset_path": (root / "dataset").as_posix(),
                "task_type": "sequence_regression",
                "training_runs": [{"run_id": run_id, "status": "completed"}],
            }

            registry = ExperimentRunRegistry.build(project)

            self.assertEqual(registry["run_count"], 1)
            run = registry["runs"][0]
            self.assertEqual(run["architecture"], "rnn")
            self.assertTrue(run["model"]["present"])
            self.assertGreaterEqual(run["artifact_counts"]["model"], 1)

    def test_rnn_export_creates_task_aware_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            run_id = "run_rnn_lstm_001"
            write_rnn_run(root, run_id)
            project = {
                "project_id": "proj",
                "dataset_path": (root / "dataset").as_posix(),
                "task_type": "sequence_regression",
                "training_runs": [{"run_id": run_id, "status": "completed"}],
                "rnn_config": {"sequence_length": 8, "stride": 2, "horizon": 1},
            }

            with patch("src.training.export_service.ProjectManager.save_project", return_value=True):
                result = ExportService.export_project_model("proj", project, run_id=run_id)

            self.assertEqual(result["export_type"], "rnn_model_package")
            package_path = Path(result["package_path"])
            self.assertTrue(package_path.exists())
            summary = json.loads((root / "exports" / result["export_id"] / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["inference_contract"]["architecture"], "rnn")
            self.assertIn("preprocess/feature_schema.json", {item["path"] for item in summary["files"]})

    def test_rnn_export_can_write_contract_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            run_id = "run_rnn_lstm_001"
            write_rnn_run(root, run_id)
            project = {
                "project_id": "proj",
                "dataset_path": (root / "dataset").as_posix(),
                "task_type": "sequence_regression",
                "training_runs": [{"run_id": run_id, "status": "completed"}],
            }

            with patch("src.training.export_service.ProjectManager.save_project", return_value=True):
                result = ExportService.export_project_model("proj", project, run_id=run_id, export_format="rnn_contract")

            self.assertEqual(result["export_type"], "rnn_inference_contract")
            contract_path = Path(result["contract_path"])
            self.assertTrue(contract_path.exists())
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            self.assertEqual(contract["architecture"], "rnn")
            self.assertEqual(contract["run_id"], run_id)

    def test_rnn_export_can_write_schema_scaler_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            run_id = "run_rnn_lstm_001"
            write_rnn_run(root, run_id)
            project = {
                "project_id": "proj",
                "dataset_path": (root / "dataset").as_posix(),
                "task_type": "sequence_regression",
                "training_runs": [{"run_id": run_id, "status": "completed"}],
            }

            with patch("src.training.export_service.ProjectManager.save_project", return_value=True):
                result = ExportService.export_project_model("proj", project, run_id=run_id, export_format="rnn_schema_scaler")

            self.assertEqual(result["export_type"], "rnn_schema_scaler_package")
            package_path = Path(result["package_path"])
            self.assertTrue(package_path.exists())
            summary = json.loads((root / "exports" / result["export_id"] / "summary.json").read_text(encoding="utf-8"))
            self.assertIn("preprocess/feature_schema.json", {item["path"] for item in summary["files"]})
            self.assertIn("preprocess/normalization_stats.json", {item["path"] for item in summary["files"]})


if __name__ == "__main__":
    unittest.main()
