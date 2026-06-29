import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.training.backends.rnn_backend import RNNBackend
from src.training.dispatcher import TrainerDispatcher
from src.training.rnn.sequence_dataset import RNNSequenceDatasetError, load_csv_feature_sequences
from src.training.state_store import TrainingStateStore


class RNNBackendMVPTests(unittest.TestCase):
    def setUp(self):
        TrainingStateStore._states.clear()

    def _project(self, root: Path) -> dict:
        dataset_dir = root / "dataset"
        dataset_dir.mkdir(parents=True, exist_ok=True)
        return {
            "project_id": "proj_rnn_mvp",
            "project_name": "rnn mvp",
            "dataset_path": dataset_dir.as_posix(),
            "training_config": {
                "backend": "pytorch_lstm",
                "model": "lstm",
                "epochs": 1,
                "batch_size": 2,
                "lr0": 0.001,
                "device": "cpu",
                "run_id": "run_rnn_unit",
                "sequence_length": 2,
                "stride": 1,
                "task_head": "classification",
            },
        }

    def _write_csv(self, root: Path) -> None:
        sequences_dir = root / "sequences"
        sequences_dir.mkdir(parents=True, exist_ok=True)
        rows = [
            "sequence_id,timestep,split,feature_1,feature_2,label",
            "seq_train,0,train,0.1,0.2,normal",
            "seq_train,1,train,0.2,0.3,normal",
            "seq_train,2,train,0.3,0.4,normal",
            "seq_val,0,val,0.7,0.8,abnormal",
            "seq_val,1,val,0.8,0.9,abnormal",
            "seq_val,2,val,0.9,1.0,abnormal",
        ]
        (sequences_dir / "features.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")

    def test_dispatcher_registers_pytorch_lstm_without_changing_default(self):
        self.assertEqual(TrainerDispatcher.resolve_backend({}).backend_name, "ultralytics_yolo")
        backend = TrainerDispatcher.resolve_backend({"training_config": {"backend": "pytorch_lstm"}})
        self.assertEqual(backend.backend_name, "pytorch_lstm")
        self.assertEqual(backend.architecture, "rnn")

    def test_csv_feature_sequence_loader_builds_train_val_windows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = self._project(root)
            self._write_csv(root)

            dataset = load_csv_feature_sequences(project, sequence_length=2, stride=1)

            self.assertEqual(dataset["input_dim"], 2)
            self.assertEqual(dataset["task_head"], "classification")
            self.assertEqual(dataset["summary"]["split_counts"]["train"], 2)
            self.assertEqual(dataset["summary"]["split_counts"]["val"], 2)
            self.assertEqual(dataset["tensors"]["train"]["x"].shape, (2, 2, 2))

    def test_csv_feature_sequence_loader_rejects_missing_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = self._project(Path(temp_dir))

            with self.assertRaisesRegex(RNNSequenceDatasetError, "CSV feature sequence files"):
                load_csv_feature_sequences(project, sequence_length=2, stride=1)

    def test_backend_readiness_accepts_csv_and_rejects_cnn_lstm(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = self._project(root)
            self._write_csv(root)
            backend = RNNBackend()

            self.assertEqual(backend.validate_readiness(project, project["training_config"]), [])
            bad_config = dict(project["training_config"], model="cnn_lstm")
            errors = backend.validate_readiness(project, bad_config)
            self.assertTrue(any("CNN-LSTM" in error for error in errors))

    def test_backend_readiness_rejects_manifest_only_sources(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = self._project(root)
            sequences_dir = root / "sequences"
            sequences_dir.mkdir(parents=True)
            manifest = {
                "sequences": [
                    {"sequence_id": "train_seq", "split": "train", "label": "normal", "feature_dim": 2, "length": 2},
                    {"sequence_id": "val_seq", "split": "val", "label": "abnormal", "feature_dim": 2, "length": 2},
                ]
            }
            (sequences_dir / "sequence_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            errors = RNNBackend().validate_readiness(project, project["training_config"])

            self.assertTrue(any("CSV feature sequence" in error for error in errors))

    def test_run_training_writes_rnn_contracts_without_real_torch_training(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = self._project(root)
            self._write_csv(root)
            backend = RNNBackend()

            fake_metrics = {
                "best_epoch": 1,
                "best_metrics": {"epoch": 1, "train/loss": 0.1, "val/loss": 0.2, "val/macro_f1": 1.0},
                "history": [{"epoch": 1, "train/loss": 0.1, "val/loss": 0.2, "val/macro_f1": 1.0}],
                "dataset_summary": {"window_count": 4},
            }

            def fake_train(dataset, run_dir, config, stop_requested=None, progress_callback=None):
                weights = run_dir / "weights"
                weights.mkdir(parents=True, exist_ok=True)
                (weights / "best.pt").write_bytes(b"best")
                (weights / "last.pt").write_bytes(b"last")
                (run_dir / "metrics.json").write_text(json.dumps(fake_metrics), encoding="utf-8")
                (run_dir / "results.csv").write_text("epoch,train/loss,val/loss,val/macro_f1\n1,0.1,0.2,1.0\n", encoding="utf-8")
                if progress_callback:
                    progress_callback(fake_metrics["history"][0])
                return fake_metrics

            with patch("src.training.backends.rnn_backend.ProjectManager.save_project"), patch(
                "src.training.backends.rnn_backend.train_rnn_from_dataset",
                side_effect=fake_train,
            ):
                backend._run_training(project)

            run_dir = root / "training" / "runs" / "run_rnn_unit"
            self.assertTrue(run_dir.joinpath("backend.json").exists())
            self.assertTrue(run_dir.joinpath("metric_schema.json").exists())
            self.assertTrue(run_dir.joinpath("artifact_manifest.json").exists())
            self.assertTrue(run_dir.joinpath("preprocess", "feature_schema.json").exists())
            backend_contract = json.loads(run_dir.joinpath("backend.json").read_text(encoding="utf-8"))
            self.assertEqual(backend_contract["architecture"], "rnn")
            self.assertEqual(backend_contract["backend"], "pytorch_lstm")
            self.assertEqual(TrainingStateStore.get_state("proj_rnn_mvp")["status"], "completed")


if __name__ == "__main__":
    unittest.main()
