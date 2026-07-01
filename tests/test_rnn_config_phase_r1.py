import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.training.rnn.sequence_dataset import load_csv_feature_sequences
from src.training.rnn_config import (
    build_window_summary,
    compute_feature_config_hash,
    find_config_mismatches,
    import_sequence_dataset,
    parse_feature_columns,
    update_project_rnn_config,
    validate_rnn_config,
)


class _Upload:
    def __init__(self, path: Path):
        self.filename = path.name
        self.file = path.open("rb")


def _write_csv(path: Path, rows: int = 8) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["sequence_id", "timestep", "split", "speed", "rpm", "temp", "target"],
        )
        writer.writeheader()
        for seq_id, split, target in [("a", "train", "ok"), ("b", "val", "ng")]:
            for step in range(rows):
                writer.writerow(
                    {
                        "sequence_id": seq_id,
                        "timestep": step,
                        "split": split,
                        "speed": 10 + step,
                        "rpm": 100 + step,
                        "temp": 20 + step,
                        "target": target,
                    }
                )


class RNNConfigPhaseR1Tests(unittest.TestCase):
    def test_parse_feature_columns_supports_comma_semicolon_and_newline(self):
        self.assertEqual(
            parse_feature_columns("speed, rpm;temp，pressure\nspeed"),
            ["speed", "rpm", "temp", "pressure"],
        )

    def test_import_sequence_dataset_writes_manifest_and_suggested_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj_rnn"
            source = Path(tmp) / "sample.csv"
            _write_csv(source)
            project = {
                "project_id": "proj_rnn",
                "dataset_path": (root / "dataset").as_posix(),
                "task_type": "sequence_classification",
            }
            upload = _Upload(source)
            try:
                result = import_sequence_dataset(project, upload)
            finally:
                upload.file.close()

            self.assertEqual(result["suggested_config"]["feature_columns"], ["speed", "rpm", "temp"])
            self.assertEqual(result["suggested_config"]["target_column"], "target")
            self.assertTrue((root / "sequences" / "sequence_manifest.json").exists())
            self.assertTrue((root / "sequences" / "sample.csv").exists())

    def test_update_config_generates_hash_and_detects_run_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj_rnn"
            _write_csv(root / "sequences" / "sample.csv")
            old_hash = compute_feature_config_hash(
                {
                    "feature_columns": ["speed"],
                    "target_column": "target",
                    "sequence_column": "sequence_id",
                    "time_column": "timestep",
                    "sequence_length": 4,
                    "stride": 2,
                    "horizon": 1,
                    "task_head": "classification",
                }
            )
            project = {
                "project_id": "proj_rnn",
                "dataset_path": (root / "dataset").as_posix(),
                "task_type": "sequence_classification",
                "training_runs": [
                    {
                        "run_id": "run_rnn_old",
                        "architecture": "rnn",
                        "backend": "pytorch_lstm",
                        "feature_config_hash": old_hash,
                    }
                ],
            }
            with patch("src.training.rnn_config.ProjectManager.save_project", return_value=True):
                result = update_project_rnn_config(
                    "proj_rnn",
                    project,
                    {
                        "feature_columns": ["speed", "rpm"],
                        "target_column": "target",
                        "sequence_column": "sequence_id",
                        "time_column": "timestep",
                        "sequence_length": 4,
                        "stride": 2,
                        "horizon": 1,
                        "task_head": "classification",
                    },
                )
            self.assertTrue(result["validation"]["valid"])
            self.assertNotEqual(result["config"]["feature_config_hash"], old_hash)
            self.assertEqual(result["mismatches"][0]["run_id"], "run_rnn_old")
            self.assertEqual(find_config_mismatches(project)[0]["status"], "config_mismatch")

    def test_sequence_dataset_uses_active_feature_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj_rnn"
            _write_csv(root / "sequences" / "sample.csv")
            project = {
                "project_id": "proj_rnn",
                "dataset_path": (root / "dataset").as_posix(),
                "task_type": "sequence_classification",
                "rnn_config": {
                    "feature_columns": ["speed", "rpm"],
                    "target_column": "target",
                    "sequence_column": "sequence_id",
                    "time_column": "timestep",
                    "sequence_length": 4,
                    "stride": 2,
                    "horizon": 1,
                    "task_head": "classification",
                },
            }
            dataset = load_csv_feature_sequences(project, sequence_length=4, stride=2)
            self.assertEqual(dataset["feature_columns"], ["speed", "rpm"])
            self.assertEqual(dataset["input_dim"], 2)
            self.assertTrue(dataset["feature_config_hash"])

    def test_window_summary_estimates_training_windows(self):
        inspection = {
            "headers": ["sequence_id", "timestep", "speed", "target"],
            "headers_match": True,
            "sequence_lengths": {"a": 8, "b": 8},
            "sequence_count": 2,
        }
        config = {
            "feature_columns": ["speed"],
            "target_column": "target",
            "sequence_column": "sequence_id",
            "time_column": "timestep",
            "sequence_length": 4,
            "stride": 2,
            "horizon": 1,
        }
        summary = build_window_summary(config, inspection)
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["estimated_windows"], 6)
        self.assertEqual(summary["min_sequence_length"], 8)

    def test_window_validation_rejects_unusable_sequence_length(self):
        inspection = {
            "headers": ["sequence_id", "timestep", "speed", "target"],
            "headers_match": True,
            "sequence_lengths": {"a": 3, "b": 3},
            "sequence_count": 2,
        }
        config = {
            "feature_columns": ["speed"],
            "target_column": "target",
            "sequence_column": "sequence_id",
            "time_column": "timestep",
            "sequence_length": 8,
            "stride": 1,
            "horizon": 1,
        }
        validation = validate_rnn_config(config, inspection)
        self.assertFalse(validation["valid"])
        self.assertEqual(validation["window"]["status"], "error")


if __name__ == "__main__":
    unittest.main()
