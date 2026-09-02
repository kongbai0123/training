import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.api.routes.evaluation import get_evaluation_results
from src.project_layout import ProjectLayout


class UnifiedEvaluationContractTests(unittest.TestCase):
    def _project(self, root: Path, project_id: str, architecture: str, task_type: str):
        return {
            "project_id": project_id,
            "dataset_path": str(root / "dataset"),
            "layout": {"mode": "v3"},
            "architecture": architecture,
            "task_type": task_type,
            "training_runs": [{
                "run_id": "run_done",
                "status": "completed",
                "completed_at": "2026-09-02T10:00:00",
            }],
        }

    def _write_run(self, project, metrics):
        run_dir = ProjectLayout.from_project(project).training_run_dir("run_done")
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "metrics.json").write_text(
            json.dumps(metrics, ensure_ascii=False), encoding="utf-8"
        )
        (run_dir / "run_summary.json").write_text(
            json.dumps({
                "status": "completed",
                "architecture": project["architecture"],
                "task_type": project["task_type"],
            }),
            encoding="utf-8",
        )
        return run_dir

    def test_tabular_classification_uses_shared_metrics_and_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp), "tab_eval", "tabular", "tabular_classification")
            self._write_run(project, {
                "architecture": "tabular",
                "backend": "xgboost_tabular",
                "task_type": "tabular_classification",
                "history": [{
                    "epoch": 1,
                    "train/loss": 0.3,
                    "val/loss": 0.4,
                    "val/accuracy": 0.91,
                    "val/macro_f1": 0.88,
                    "val/precision": 0.9,
                    "val/recall": 0.87,
                }],
                "best_metrics": {"val/macro_f1": 0.88, "val/accuracy": 0.91},
                "confusion_labels": ["good", "bad"],
                "confusion_matrix": [[8, 1], [1, 10]],
                "feature_importance": [{"feature": "temperature", "normalized_gain": 1.0}],
            })

            with patch("src.api.routes.evaluation.ProjectManager.get_project", return_value=project):
                payload = get_evaluation_results("tab_eval")

            self.assertEqual(payload["architecture"], "tabular")
            self.assertEqual(payload["metric_schema"]["primary_metric"]["key"], "val/macro_f1")
            self.assertIn("val/macro_f1", {card["key"] for card in payload["metric_cards"]})
            self.assertTrue(payload["capabilities"]["row_context"])
            self.assertTrue(payload["capabilities"]["confusion_matrix"])
            self.assertTrue(payload["capabilities"]["feature_importance"])
            self.assertFalse(payload["capabilities"]["image_plots"])
            self.assertEqual(payload["assessment"]["verdict"], "review")
            self.assertEqual(payload["assessment"]["score"], 88)

    def test_rnn_regression_exposes_residuals_without_image_assumptions(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp), "rnn_eval", "rnn", "sequence_regression")
            self._write_run(project, {
                "architecture": "rnn",
                "backend": "pytorch_rnn",
                "task_type": "sequence_regression",
                "history": [{
                    "epoch": 1,
                    "train/loss": 0.2,
                    "val/loss": 0.25,
                    "val/mae": 0.12,
                    "val/rmse": 0.18,
                    "val/r2": 0.82,
                }],
                "best_metrics": {"val/mae": 0.12, "val/rmse": 0.18, "val/r2": 0.82},
                "residuals": [0.1, -0.2],
                "prediction_actual_samples": [
                    {"actual": 1.0, "prediction": 1.1, "residual": 0.1},
                ],
            })

            with patch("src.api.routes.evaluation.ProjectManager.get_project", return_value=project):
                payload = get_evaluation_results("rnn_eval")

            self.assertEqual(payload["architecture"], "rnn")
            self.assertEqual(payload["metric_schema"]["primary_metric"]["key"], "val/mae")
            self.assertTrue(payload["capabilities"]["sequence_context"])
            self.assertTrue(payload["capabilities"]["residual_analysis"])
            self.assertFalse(payload["capabilities"]["image_plots"])
            self.assertEqual(payload["diagnostics"]["residuals"], [0.1, -0.2])
            self.assertEqual(payload["assessment"]["score"], 82)


if __name__ == "__main__":
    unittest.main()
