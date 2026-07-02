import json
import tempfile
import unittest
from pathlib import Path

from app import _latest_completed_training_run_dir
from src.project_layout import ProjectLayout


class CnnEvaluationCompletedOnlyTests(unittest.TestCase):
    def _layout(self, root: Path) -> ProjectLayout:
        project = {
            "project_id": "proj_eval",
            "dataset_path": str(root / "dataset"),
            "layout": {"mode": "v3"},
        }
        return ProjectLayout.from_project(project)

    def test_completed_project_run_can_supply_evaluation_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj_eval"
            layout = self._layout(root)
            run_dir = layout.training_run_dir("run_done")
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "metrics.json").write_text("{}", encoding="utf-8")

            project = {
                "training_runs": [
                    {"run_id": "run_done", "status": "completed", "completed_at": "2026-07-02T10:00:00"}
                ]
            }

            self.assertEqual(_latest_completed_training_run_dir(project, layout), run_dir)

    def test_training_project_run_is_not_used_for_evaluation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj_eval"
            layout = self._layout(root)
            run_dir = layout.training_run_dir("run_live")
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "metrics.json").write_text("{}", encoding="utf-8")

            project = {
                "training_runs": [
                    {"run_id": "run_live", "status": "training", "created_at": "2026-07-02T10:00:00"}
                ]
            }

            self.assertIsNone(_latest_completed_training_run_dir(project, layout))

    def test_untracked_run_requires_completed_summary_for_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj_eval"
            layout = self._layout(root)
            run_dir = layout.training_run_dir("run_probe")
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "metrics.json").write_text("{}", encoding="utf-8")

            self.assertIsNone(_latest_completed_training_run_dir({"training_runs": []}, layout))

            (run_dir / "run_summary.json").write_text(
                json.dumps({"status": "completed"}),
                encoding="utf-8",
            )

            self.assertEqual(_latest_completed_training_run_dir({"training_runs": []}, layout), run_dir)


if __name__ == "__main__":
    unittest.main()
