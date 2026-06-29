import json
import tempfile
import unittest
from pathlib import Path

from src.training.rnn_readiness import build_rnn_readiness_report


class RNNSequenceReadinessPhase2BTests(unittest.TestCase):
    def _project(self, root: Path) -> dict:
        dataset_dir = root / "dataset"
        dataset_dir.mkdir(parents=True, exist_ok=True)
        return {
            "project_id": "proj_rnn_readiness",
            "project_name": "rnn readiness",
            "dataset_path": dataset_dir.as_posix(),
        }

    def test_missing_sequence_sources_are_not_ready_and_do_not_enable_training(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = self._project(Path(temp_dir))

            report = build_rnn_readiness_report(project, sequence_length=4)

            self.assertFalse(report["ready"])
            self.assertFalse(report["training_enabled"])
            self.assertEqual(report["status"], "not_ready")
            self.assertEqual(report["summary"]["source"], "none")
            self.assertIn("sequence_manifest", {check["key"] for check in report["checks"]})
            self.assertIn("csv_feature_files", {check["key"] for check in report["checks"]})

    def test_csv_feature_sequence_readiness(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = self._project(root)
            sequences_dir = root / "sequences"
            sequences_dir.mkdir()
            rows = [
                "sequence_id,timestep,split,feature_1,feature_2,label",
                "seq_train,0,train,0.1,0.2,normal",
                "seq_train,1,train,0.2,0.3,normal",
                "seq_val,0,val,0.4,0.5,abnormal",
                "seq_val,1,val,0.5,0.6,abnormal",
            ]
            sequences_dir.joinpath("features.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")

            report = build_rnn_readiness_report(project, sequence_length=2)

            self.assertTrue(report["ready"])
            self.assertFalse(report["training_enabled"])
            self.assertEqual(report["summary"]["source"], "csv")
            self.assertEqual(report["summary"]["csv"]["feature_dim"], 2)
            self.assertEqual(report["summary"]["csv"]["sequence_count"], 2)
            self.assertEqual(report["summary"]["csv"]["split_counts"]["train"], 1)
            self.assertEqual(report["summary"]["csv"]["split_counts"]["val"], 1)

    def test_sequence_manifest_readiness(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = self._project(root)
            sequences_dir = root / "sequences"
            sequences_dir.mkdir()
            manifest = {
                "sequences": [
                    {
                        "sequence_id": "seq_train",
                        "split": "train",
                        "label": "normal",
                        "feature_dim": 3,
                        "frames": [{"t": 0}, {"t": 1}, {"t": 2}],
                    },
                    {
                        "sequence_id": "seq_val",
                        "split": "val",
                        "label": "abnormal",
                        "feature_dim": 3,
                        "frames": [{"t": 0}, {"t": 1}, {"t": 2}],
                    },
                ]
            }
            sequences_dir.joinpath("sequence_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            report = build_rnn_readiness_report(project, sequence_length=3)

            self.assertTrue(report["ready"])
            self.assertFalse(report["training_enabled"])
            self.assertEqual(report["summary"]["source"], "manifest")
            self.assertEqual(report["summary"]["manifest"]["feature_dim"], 3)
            self.assertEqual(report["summary"]["manifest"]["sequence_count"], 2)


if __name__ == "__main__":
    unittest.main()
