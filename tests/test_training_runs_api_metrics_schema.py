import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.api.routes.training_runs import get_run_metrics


class _FakeLayout:
    def __init__(self, root: Path):
        self.root = root

    def training_run_dir(self, run_id: str) -> Path:
        return self.root / "training" / "runs" / run_id


class TrainingRunsApiMetricsSchemaTests(unittest.TestCase):
    def test_get_run_metrics_includes_metric_schema_when_available(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_dir = root / "training" / "runs" / "run_rnn"
            run_dir.mkdir(parents=True)
            run_dir.joinpath("metrics.json").write_text(
                json.dumps({"task_type": "sequence_classification", "history": []}),
                encoding="utf-8",
            )
            run_dir.joinpath("metric_schema.json").write_text(
                json.dumps({"primary_metric": {"key": "val/macro_f1"}, "groups": {"quality": ["val/macro_f1"]}}),
                encoding="utf-8",
            )
            run_dir.joinpath("train_config.json").write_text(
                json.dumps({"epochs": 30}),
                encoding="utf-8",
            )

            with patch("src.api.routes.training_runs.ProjectManager.get_project", return_value={"project_id": "p1"}), \
                 patch("src.api.routes.training_runs.ProjectLayout.from_project", return_value=_FakeLayout(root)):
                payload = get_run_metrics("p1", "run_rnn")

            self.assertEqual(payload["metric_schema"]["primary_metric"]["key"], "val/macro_f1")
            self.assertEqual(payload["metric_schema"]["groups"]["quality"], ["val/macro_f1"])
            self.assertEqual(payload["run_id"], "run_rnn")
            self.assertEqual(payload["total_epochs"], 30)


if __name__ == "__main__":
    unittest.main()
