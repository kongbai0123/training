import json
import tempfile
import unittest
from pathlib import Path

from src.training.compare_service import CompareService, CompareServiceError
from src.training.metric_schema import build_rnn_metric_schema


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def make_rnn_project(root: Path, task_type: str = "sequence_classification"):
    dataset_dir = root / "dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    return {
        "project_id": "proj_rnn_compare",
        "project_name": "RNN Compare",
        "task_type": task_type,
        "dataset_path": dataset_dir.as_posix(),
    }


def write_rnn_run(
    project,
    run_id,
    *,
    task_type="sequence_classification",
    status="completed",
    metrics=None,
    config=None,
):
    project_dir = Path(project["dataset_path"]).parent
    run_dir = project_dir / "training" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "weights").mkdir(parents=True, exist_ok=True)
    (run_dir / "weights" / "best.pt").write_bytes(b"rnn-best")

    if metrics is None:
        metrics = [
            {"epoch": 1, "train/loss": 0.50, "val/loss": 0.60, "val/accuracy": 0.72, "val/macro_f1": 0.70},
            {"epoch": 2, "train/loss": 0.30, "val/loss": 0.40, "val/accuracy": 0.82, "val/macro_f1": 0.80},
        ]
    best_metrics = {key: value for key, value in metrics[-1].items() if key != "epoch"}
    if "regression" in task_type:
        best_metrics.setdefault("val/mae", metrics[-1].get("val/mae", 0.12))
        best_metrics.setdefault("val/rmse", metrics[-1].get("val/rmse", 0.18))

    write_json(
        run_dir / "metrics.json",
        {
            "history": metrics,
            "best_epoch": metrics[-1].get("epoch", len(metrics)),
            "best_metrics": best_metrics,
        },
    )
    write_json(
        run_dir / "run_summary.json",
        {
            "run_id": run_id,
            "status": status,
            "task_type": task_type,
            "architecture": "rnn",
            "backend": "pytorch_lstm",
            "best_epoch": metrics[-1].get("epoch", len(metrics)),
            "best_metrics": best_metrics,
            "platform_score": best_metrics.get("val/macro_f1", 1.0 / (1.0 + best_metrics.get("val/mae", 1.0))),
        },
    )
    write_json(
        run_dir / "train_config.json",
        config
        or {
            "backend": "pytorch_lstm",
            "model": "lstm",
            "epochs": len(metrics),
            "batch_size": 16,
            "sequence_length": 16,
            "stride": 8,
            "horizon": 1,
            "task_head": "regression" if "regression" in task_type else "classification",
            "hidden_size": 128,
            "num_layers": 2,
            "dropout": 0.2,
        },
    )
    write_json(
        run_dir / "backend.json",
        {
            "contract_version": "1.0",
            "run_id": run_id,
            "architecture": "rnn",
            "backend": "pytorch_lstm",
            "task_type": task_type,
            "status": status,
            "created_at": "2026-06-29T10:00:00",
            "completed_at": "2026-06-29T10:05:00",
            "generated_at": "2026-06-29T10:05:01",
        },
    )
    write_json(run_dir / "metric_schema.json", build_rnn_metric_schema(task_type))
    write_json(
        run_dir / "artifact_manifest.json",
        {
            "contract_version": "1.0",
            "run_id": run_id,
            "artifacts": [
                {"name": "best.pt", "type": "model_weight", "role": "best_model", "path": "weights/best.pt", "size_bytes": 8},
                {"name": "metrics.json", "type": "metrics_json", "role": "metrics", "path": "metrics.json", "size_bytes": 10},
            ],
        },
    )
    return run_dir


class CompareServicePhase3ERNNTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = make_rnn_project(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_list_completed_rnn_runs(self):
        write_rnn_run(self.project, "run_rnn_a")
        write_rnn_run(self.project, "run_rnn_failed", status="failed")

        payload = CompareService.list_comparable_runs(self.project, "rnn")

        self.assertEqual(payload["architecture"], "rnn")
        self.assertEqual([run["run_id"] for run in payload["runs"]], ["run_rnn_a"])
        self.assertEqual(payload["runs"][0]["primary_metric"]["key"], "val/macro_f1")

    def test_compare_two_rnn_classification_runs(self):
        write_rnn_run(self.project, "run_rnn_a")
        write_rnn_run(
            self.project,
            "run_rnn_b",
            metrics=[
                {"epoch": 1, "train/loss": 0.40, "val/loss": 0.50, "val/accuracy": 0.78, "val/macro_f1": 0.76},
                {"epoch": 2, "train/loss": 0.20, "val/loss": 0.30, "val/accuracy": 0.90, "val/macro_f1": 0.88},
            ],
        )

        payload = CompareService.compare_runs(self.project, "rnn", ["run_rnn_a", "run_rnn_b"], "run_rnn_a")

        self.assertEqual(payload["architecture"], "rnn")
        self.assertEqual(payload["task_family"], "classification")
        self.assertIn("val/macro_f1", payload["series"])
        self.assertEqual(payload["summary"]["best_by_metric"]["val/macro_f1"]["run_id"], "run_rnn_b")
        self.assertEqual(payload["recommendation"]["best_overall"], "run_rnn_b")

    def test_compare_two_rnn_regression_runs_uses_minimize_goal(self):
        project = make_rnn_project(self.root / "regression", "sequence_regression")
        write_rnn_run(
            project,
            "run_reg_a",
            task_type="sequence_regression",
            metrics=[
                {"epoch": 1, "train/loss": 0.40, "val/loss": 0.50, "val/mae": 0.20, "val/rmse": 0.30},
                {"epoch": 2, "train/loss": 0.30, "val/loss": 0.40, "val/mae": 0.18, "val/rmse": 0.25},
            ],
        )
        write_rnn_run(
            project,
            "run_reg_b",
            task_type="sequence_regression",
            metrics=[
                {"epoch": 1, "train/loss": 0.35, "val/loss": 0.45, "val/mae": 0.16, "val/rmse": 0.22},
                {"epoch": 2, "train/loss": 0.25, "val/loss": 0.35, "val/mae": 0.12, "val/rmse": 0.18},
            ],
        )

        payload = CompareService.compare_runs(project, "rnn", ["run_reg_a", "run_reg_b"])

        self.assertEqual(payload["task_family"], "regression")
        self.assertEqual(payload["series"]["val/mae"]["goal"], "minimize")
        self.assertEqual(payload["summary"]["best_by_metric"]["val/mae"]["run_id"], "run_reg_b")
        self.assertIn("Lowest primary metric", payload["recommendation"]["reason"])

    def test_rejects_mixed_rnn_task_family(self):
        write_rnn_run(self.project, "run_class", task_type="sequence_classification")
        write_rnn_run(self.project, "run_reg", task_type="sequence_regression")

        with self.assertRaises(CompareServiceError):
            CompareService.compare_runs(self.project, "rnn", ["run_class", "run_reg"])


if __name__ == "__main__":
    unittest.main()
