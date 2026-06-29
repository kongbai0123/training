import shutil
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from src.config import PROJECTS_DIR
from src.model_registry import ModelRegistry
from src.rnn_inference_engine import RNNSequenceInferenceEngine
from src.training.backends.rnn_backend import RNNBackend
from src.training.state_store import TrainingStateStore


class RNNSequenceInferencePhase2FTests(unittest.TestCase):
    def setUp(self):
        TrainingStateStore._states.clear()
        self.project_id = f"proj_rnn_inference_unit_{uuid4().hex[:8]}"
        self.run_id = f"run_rnn_infer_{uuid4().hex[:8]}"
        self.project_root = PROJECTS_DIR / self.project_id
        self._remove_project_root()
        self.project_root.mkdir(parents=True)
        (self.project_root / "dataset").mkdir()

    def tearDown(self):
        TrainingStateStore._states.clear()
        self._remove_project_root()

    def _remove_project_root(self):
        if self.project_root.exists():
            for _ in range(3):
                try:
                    shutil.rmtree(self.project_root)
                    return
                except OSError:
                    time.sleep(0.1)
            shutil.rmtree(self.project_root, ignore_errors=True)

    def _project(self) -> dict:
        return {
            "project_id": self.project_id,
            "project_name": "rnn inference",
            "dataset_path": (self.project_root / "dataset").as_posix(),
            "training_config": {
                "backend": "pytorch_lstm",
                "model": "lstm",
                "epochs": 1,
                "batch_size": 2,
                "lr0": 0.001,
                "device": "cpu",
                "run_id": self.run_id,
                "sequence_length": 2,
                "stride": 1,
                "task_head": "classification",
                "hidden_size": 8,
                "num_layers": 1,
            },
        }

    def _write_csv(self, filename: str = "features.csv") -> Path:
        sequences_dir = self.project_root / "sequences"
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
        path = sequences_dir / filename
        path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        return path

    def _train_rnn_model(self) -> dict:
        project = self._project()
        self._write_csv()
        with patch("src.training.backends.rnn_backend.ProjectManager.save_project"):
            RNNBackend()._run_training(project)
        models = ModelRegistry.list_models(project)
        rnn_models = [model for model in models if model.get("backend") == "pytorch_lstm"]
        self.assertTrue(rnn_models)
        return project, rnn_models[0]

    def test_csv_sequence_inference_returns_predictions_and_artifacts(self):
        project, model = self._train_rnn_model()
        input_csv = self._write_csv("inference.csv")

        result = RNNSequenceInferenceEngine.run_csv_sequence_inference(
            project=project,
            model=model,
            input_path=input_csv,
            settings={"device": "cpu"},
        )

        self.assertEqual(result["summary"]["architecture"], "rnn")
        self.assertGreaterEqual(result["summary"]["sequence_count"], 1)
        self.assertTrue(result["predictions"])
        self.assertTrue(Path(result["paths"]["prediction_json"]).exists())
        self.assertTrue(Path(result["paths"]["prediction_csv"]).exists())

    def test_sequence_inference_rejects_non_rnn_model(self):
        project = self._project()
        csv_path = self._write_csv()
        model = {
            "model_id": "fake",
            "architecture": "cnn",
            "backend": "ultralytics_yolo",
            "internal_weight_path": (self.project_root / "fake.pt").as_posix(),
        }

        with self.assertRaisesRegex(ValueError, "Only RNN"):
            RNNSequenceInferenceEngine.run_csv_sequence_inference(project, model, csv_path, {})

    def test_sequence_inference_rejects_non_csv_input(self):
        project, model = self._train_rnn_model()
        txt = self.project_root / "sequences" / "input.txt"
        txt.write_text("not csv", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "Only CSV"):
            RNNSequenceInferenceEngine.run_csv_sequence_inference(project, model, txt, {})


if __name__ == "__main__":
    unittest.main()
