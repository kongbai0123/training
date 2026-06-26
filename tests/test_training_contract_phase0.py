import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.model_registry import ModelRegistry
from src.training.artifact_manifest import build_artifact_manifest
from src.training.contracts import build_backend_contract
from src.training.metric_schema import build_yolo_metric_schema
from src.training.run_manager import RunManager


def _write_fake_results_csv(run_dir: Path, suffix: str = "(B)") -> None:
    headers = [
        "epoch",
        f"metrics/mAP50{suffix}",
        f"metrics/mAP50-95{suffix}",
        f"metrics/precision{suffix}",
        f"metrics/recall{suffix}",
        "train/box_loss",
        "val/box_loss",
    ]
    rows = [
        ["1", "0.40", "0.30", "0.50", "0.60", "1.20", "1.30"],
        ["2", "0.50", "0.35", "0.55", "0.65", "1.00", "1.10"],
    ]
    run_dir.joinpath("results.csv").write_text(
        ",".join(headers) + "\n" + "\n".join(",".join(row) for row in rows) + "\n",
        encoding="utf-8",
    )


class TrainingContractPhase0Tests(unittest.TestCase):
    def test_backend_contract_and_metric_schema_fields(self):
        contract = build_backend_contract(
            run_id="run_20260626_101500",
            architecture="cnn",
            backend="ultralytics_yolo",
            task_type="segmentation",
            status="completed",
            created_at="2026-06-26T10:15:00",
            completed_at="2026-06-26T10:58:00",
        )
        self.assertEqual(contract["contract_version"], "1.0")
        self.assertEqual(contract["architecture"], "cnn")
        self.assertEqual(contract["backend"], "ultralytics_yolo")
        self.assertTrue(contract["generated_at"])

        schema = build_yolo_metric_schema("segmentation")
        self.assertEqual(schema["contract_version"], "1.0")
        self.assertEqual(schema["primary_metric"]["key"], "metrics/mAP50-95(M)")
        self.assertEqual(schema["primary_metric"]["display_name"], "mAP50-95")
        self.assertEqual(schema["primary_metric"]["goal"], "maximize")
        self.assertIn("loss", schema["groups"])
        self.assertIn("quality", schema["groups"])

        detection_schema = build_yolo_metric_schema("detection")
        self.assertEqual(detection_schema["primary_metric"]["key"], "metrics/mAP50-95(B)")

    def test_artifact_manifest_uses_existing_relative_paths_and_size(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "run_20260626_101500"
            weights_dir = run_dir / "weights"
            weights_dir.mkdir(parents=True)
            weights_dir.joinpath("best.pt").write_bytes(b"fake-weight")
            run_dir.joinpath("results.csv").write_text("epoch\n1\n", encoding="utf-8")

            manifest = build_artifact_manifest(run_dir, run_dir.name)
            artifacts = {item["path"]: item for item in manifest["artifacts"]}

            self.assertEqual(manifest["contract_version"], "1.0")
            self.assertTrue(manifest["generated_at"])
            self.assertIn("weights/best.pt", artifacts)
            self.assertEqual(artifacts["weights/best.pt"]["size_bytes"], len(b"fake-weight"))
            self.assertNotIn("sha256", artifacts["weights/best.pt"])
            self.assertFalse(Path(artifacts["weights/best.pt"]["path"]).is_absolute())
            self.assertNotIn("weights/last.pt", artifacts)

    def test_run_manager_writes_contract_files_for_completed_run(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "run_20260626_101500"
            run_dir.joinpath("weights").mkdir(parents=True)
            run_dir.joinpath("weights", "best.pt").write_bytes(b"best")
            _write_fake_results_csv(run_dir)

            summary = RunManager.finalize_run(
                run_dir=run_dir,
                task_type="detection",
                status="completed",
                error_msg="",
            )

            self.assertEqual(summary["status"], "completed")
            self.assertTrue(run_dir.joinpath("metrics.json").exists())
            self.assertTrue(run_dir.joinpath("run_summary.json").exists())
            self.assertTrue(run_dir.joinpath("backend.json").exists())
            self.assertTrue(run_dir.joinpath("metric_schema.json").exists())
            self.assertTrue(run_dir.joinpath("artifact_manifest.json").exists())

            backend = json.loads(run_dir.joinpath("backend.json").read_text(encoding="utf-8"))
            self.assertEqual(backend["architecture"], "cnn")
            self.assertEqual(backend["backend"], "ultralytics_yolo")
            self.assertTrue(backend["generated_at"])

            manifest = json.loads(run_dir.joinpath("artifact_manifest.json").read_text(encoding="utf-8"))
            paths = {item["path"] for item in manifest["artifacts"]}
            self.assertIn("metrics.json", paths)
            self.assertIn("run_summary.json", paths)
            self.assertIn("weights/best.pt", paths)

    def test_run_manager_writes_contract_files_for_failed_incomplete_run(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "run_20260626_102000"

            summary = RunManager.finalize_run(
                run_dir=run_dir,
                task_type="detection",
                status="failed",
                error_msg="boom",
            )

            self.assertEqual(summary["status"], "failed")
            self.assertTrue(run_dir.joinpath("error.log").exists())
            self.assertTrue(run_dir.joinpath("run_summary.json").exists())
            self.assertTrue(run_dir.joinpath("backend.json").exists())
            self.assertTrue(run_dir.joinpath("metric_schema.json").exists())
            self.assertTrue(run_dir.joinpath("artifact_manifest.json").exists())

            manifest = json.loads(run_dir.joinpath("artifact_manifest.json").read_text(encoding="utf-8"))
            paths = {item["path"] for item in manifest["artifacts"]}
            self.assertIn("error.log", paths)
            self.assertIn("run_summary.json", paths)

    def test_model_registry_manifest_metadata_and_legacy_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            projects_root = Path(temp_dir)
            project_dir = projects_root / "project_a"
            legacy_run = project_dir / "training" / "runs" / "run_20260626_101500"
            legacy_weights = legacy_run / "weights"
            legacy_weights.mkdir(parents=True)
            legacy_weights.joinpath("best.pt").write_bytes(b"legacy")

            manifest_run = project_dir / "training" / "runs" / "run_20260626_102000"
            manifest_weights = manifest_run / "weights"
            manifest_weights.mkdir(parents=True)
            manifest_weights.joinpath("best.pt").write_bytes(b"manifest")
            manifest_run.joinpath("backend.json").write_text(
                json.dumps(
                    {
                        "contract_version": "1.0",
                        "run_id": manifest_run.name,
                        "architecture": "cnn",
                        "backend": "ultralytics_yolo",
                        "task_type": "detection",
                        "status": "completed",
                        "created_at": "2026-06-26T10:20:00",
                        "completed_at": "2026-06-26T10:30:00",
                        "generated_at": "2026-06-26T10:30:01",
                    }
                ),
                encoding="utf-8",
            )
            manifest_run.joinpath("artifact_manifest.json").write_text(
                json.dumps(
                    {
                        "contract_version": "1.0",
                        "run_id": manifest_run.name,
                        "generated_at": "2026-06-26T10:30:01",
                        "artifacts": [
                            {
                                "name": "best.pt",
                                "type": "model_weight",
                                "role": "best_model",
                                "path": "weights/best.pt",
                                "size_bytes": 8,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            project = {
                "project_id": "project_a",
                "dataset_path": str(project_dir / "dataset"),
                "task_type": "detection",
            }

            with patch("src.model_registry.PROJECTS_DIR", projects_root):
                models = ModelRegistry.list_models(project)

            by_run = {model["run_id"]: model for model in models}
            self.assertEqual(
                by_run["run_20260626_101500"]["model_id"],
                "project_a::run_20260626_101500::best",
            )
            self.assertNotIn("architecture", by_run["run_20260626_101500"])

            manifest_model = by_run["run_20260626_102000"]
            self.assertEqual(
                manifest_model["model_id"],
                "project_a::run_20260626_102000::best",
            )
            self.assertEqual(manifest_model["architecture"], "cnn")
            self.assertEqual(manifest_model["backend"], "ultralytics_yolo")
            self.assertEqual(manifest_model["artifact_role"], "best_model")
            self.assertEqual(manifest_model["artifact_source"], "artifact_manifest")
            self.assertEqual(manifest_model["source"], "project_training_runs")


if __name__ == "__main__":
    unittest.main()
