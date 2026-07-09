import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.training.rnn.sequence_dataset import load_csv_feature_sequences
from src.training.rnn_config import (
    build_schema_wizard,
    build_window_summary,
    compute_feature_config_hash,
    find_config_mismatches,
    import_sequence_dataset,
    inspect_sequence_csv_files,
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


def _write_single_series_csv(path: Path, rows: int = 20) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["Date Time", "pressure", "humidity", "T (degC)"],
        )
        writer.writeheader()
        for step in range(rows):
            writer.writerow(
                {
                    "Date Time": f"2026-01-01 00:{step:02d}:00",
                    "pressure": 990 + step,
                    "humidity": 60 + (step % 5),
                    "T (degC)": 20 + (step * 0.1),
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
            self.assertEqual(result["suggested_config"]["task_head"], "classification")
            self.assertTrue((root / "sequences" / "sequence_manifest.json").exists())
            self.assertTrue((root / "sequences" / "sample.csv").exists())

    def test_schema_recommendation_does_not_hardcode_numeric_weather_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "weather.csv"
            _write_single_series_csv(source)

            inspection = inspect_sequence_csv_files([source])
            suggested = inspection["suggested_config"]

            self.assertEqual(suggested["task_head"], "regression")
            self.assertEqual(suggested["time_column"], "Date Time")
            self.assertEqual(suggested["target_column"], "")
            self.assertEqual(suggested["recommendation_confidence"], "needs_user")
            self.assertIn("T (degC)", suggested["feature_columns"])

    def test_schema_wizard_marks_target_manual_when_no_generic_target_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "weather.csv"
            _write_single_series_csv(source)
            inspection = inspect_sequence_csv_files([source])
            project = {
                "project_id": "proj_rnn",
                "dataset_path": (Path(tmp) / "proj_rnn" / "dataset").as_posix(),
                "task_type": "sequence_regression",
            }

            wizard = build_schema_wizard(project, inspection)

            self.assertEqual(wizard["target_status"], "manual_required")
            self.assertEqual(wizard["recommendation"]["target_column"], "")
            roles = {column["name"]: column["recommended_role"] for column in wizard["columns"]}
            self.assertEqual(roles["Date Time"], "time")
            self.assertEqual(roles["T (degC)"], "feature")

    def test_schema_recommendation_detects_numeric_target_as_regression(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "numeric_target.csv"
            source.parent.mkdir(parents=True, exist_ok=True)
            with source.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["sequence_id", "timestep", "sensor_a", "sensor_b", "target"])
                writer.writeheader()
                for seq_id in ["train_a", "val_b"]:
                    for step in range(8):
                        writer.writerow({
                            "sequence_id": seq_id,
                            "timestep": step,
                            "sensor_a": step * 0.1,
                            "sensor_b": step * 0.2,
                            "target": step * 1.5,
                        })

            suggested = inspect_sequence_csv_files([source])["suggested_config"]

            self.assertEqual(suggested["task_head"], "regression")
            self.assertEqual(suggested["target_column"], "target")
            self.assertEqual(suggested["feature_columns"], ["sensor_a", "sensor_b"])

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
            self.assertEqual(project["task_type"], "sequence_classification")
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

    def test_sequence_dataset_supports_single_continuous_series_without_sequence_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj_rnn"
            _write_single_series_csv(root / "sequences" / "weather.csv")
            project = {
                "project_id": "proj_rnn",
                "dataset_path": (root / "dataset").as_posix(),
                "task_type": "sequence_regression",
                "rnn_config": {
                    "feature_columns": ["pressure", "humidity"],
                    "target_column": "T (degC)",
                    "sequence_column": "",
                    "time_column": "Date Time",
                    "sequence_length": 4,
                    "stride": 2,
                    "horizon": 1,
                    "task_head": "regression",
                },
            }
            dataset = load_csv_feature_sequences(project, sequence_length=4, stride=2, task_head="regression")
            self.assertEqual(dataset["sequence_column"], "")
            self.assertEqual(dataset["summary"]["sequence_count"], 1)
            self.assertIn("train", dataset["tensors"])
            self.assertIn("val", dataset["tensors"])

    def test_validation_allows_empty_sequence_column_for_single_series_csv(self):
        inspection = {
            "headers": ["Date Time", "pressure", "humidity", "T (degC)"],
            "headers_match": True,
            "row_count": 20,
            "sequence_lengths": {},
            "sequence_count": 0,
        }
        config = {
            "feature_columns": ["pressure", "humidity"],
            "target_column": "T (degC)",
            "sequence_column": "",
            "time_column": "Date Time",
            "sequence_length": 4,
            "stride": 2,
            "horizon": 1,
        }
        validation = validate_rnn_config(config, inspection)
        self.assertTrue(validation["valid"])
        self.assertEqual(validation["window"]["sequence_count"], 1)
        self.assertGreater(validation["window"]["estimated_windows"], 0)

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
