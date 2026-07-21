import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.training.backends import xgboost_backend as xgboost_backend_module
from src.training.backends.xgboost_backend import XGBoostBackend
from src.training.dispatcher import TrainerDispatcher
from src.training.rnn.xgboost_trainer import _history_from_evals
from src.training.state_store import TrainingStateStore


class XGBoostBackendPhaseR1FTests(unittest.TestCase):
    def setUp(self):
        TrainingStateStore._states.clear()

    def _project(self, root: Path, task_head: str = "classification") -> dict:
        dataset_dir = root / "dataset"
        dataset_dir.mkdir(parents=True, exist_ok=True)
        model = "xgboost_regressor" if task_head == "regression" else "xgboost_classifier"
        return {
            "project_id": "proj_xgb",
            "project_name": "xgb baseline",
            "dataset_path": dataset_dir.as_posix(),
            "task_type": f"sequence_{task_head}",
            "training_config": {
                "backend": "sklearn_xgboost",
                "model": model,
                "epochs": 3,
                "batch_size": 2,
                "lr0": 0.05,
                "device": "cpu",
                "run_id": "run_xgb_unit",
                "sequence_length": 2,
                "stride": 1,
                "task_head": task_head,
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

    def test_dispatcher_registers_sklearn_xgboost_backend(self):
        backend = TrainerDispatcher.resolve_backend({"training_config": {"backend": "sklearn_xgboost"}})
        self.assertEqual(backend.backend_name, "sklearn_xgboost")
        self.assertEqual(backend.architecture, "rnn")

    def test_regression_history_contains_mae_and_rmse_for_every_round(self):
        history = _history_from_evals(
            {
                "train": {"rmse": [3.0, 2.0], "mae": [2.5, 1.5]},
                "val": {"rmse": [4.0, 3.0], "mae": [3.5, 2.5]},
            },
            is_regression=True,
        )

        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["val/rmse"], 4.0)
        self.assertEqual(history[0]["val/mae"], 3.5)
        self.assertEqual(history[1]["val/rmse"], 3.0)
        self.assertEqual(history[1]["val/mae"], 2.5)

    def test_start_training_sets_regression_task_type_and_starts_runner(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = self._project(Path(temp_dir), task_head="regression")
            backend = XGBoostBackend()
            runner_result = {
                "started": True,
                "project_id": "proj_xgb",
                "run_id": "run_xgb_unit",
                "thread_name": "training-proj_xgb-run_xgb_unit",
            }

            with patch.object(
                xgboost_backend_module.DEFAULT_THREAD_TRAINING_RUNNER,
                "start",
                return_value=runner_result,
            ) as start:
                result = backend.start_training(project)

            self.assertEqual(result["status"], "started")
            self.assertEqual(TrainingStateStore.get_state("proj_xgb")["task_type"], "sequence_regression")
            start.assert_called_once()

    def test_start_training_recovers_stale_training_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = self._project(Path(temp_dir), task_head="regression")
            backend = XGBoostBackend()
            TrainingStateStore.init_run("proj_xgb", "stale_run", 40, "rnn", "sklearn_xgboost")

            with patch.object(
                xgboost_backend_module.DEFAULT_THREAD_TRAINING_RUNNER,
                "start",
                return_value={"started": True, "run_id": "run_xgb_unit"},
            ):
                result = backend.start_training(project)

            state = TrainingStateStore.get_state("proj_xgb")
            self.assertEqual(result["status"], "started")
            self.assertEqual(state["status"], "training")
            self.assertEqual(state["run_id"], "run_xgb_unit")

    def test_start_training_marks_failed_when_runner_raises(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = self._project(Path(temp_dir), task_head="regression")
            backend = XGBoostBackend()

            with patch.object(
                xgboost_backend_module.DEFAULT_THREAD_TRAINING_RUNNER,
                "start",
                side_effect=RuntimeError("runner failed"),
            ):
                with self.assertRaisesRegex(RuntimeError, "runner failed"):
                    backend.start_training(project)

            state = TrainingStateStore.get_state("proj_xgb")
            self.assertEqual(state["status"], "failed")
            self.assertEqual(state["error"], "runner failed")

    def test_run_training_writes_xgboost_contracts_without_real_xgboost_training(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = self._project(root)
            self._write_csv(root)
            backend = XGBoostBackend()

            fake_metrics = {
                "best_epoch": 3,
                "best_metrics": {
                    "epoch": 3,
                    "train/loss": 0.1,
                    "val/loss": 0.2,
                    "val/macro_f1": 1.0,
                    "val/accuracy": 1.0,
                },
                "history": [
                    {"epoch": 1, "train/loss": 0.3, "val/loss": 0.4},
                    {"epoch": 2, "train/loss": 0.2, "val/loss": 0.3},
                    {"epoch": 3, "train/loss": 0.1, "val/loss": 0.2, "val/macro_f1": 1.0, "val/accuracy": 1.0},
                ],
                "dataset_summary": {"window_count": 4},
            }

            def fake_train(dataset, run_dir, config, stop_requested=None, progress_callback=None):
                weights = run_dir / "weights"
                weights.mkdir(parents=True, exist_ok=True)
                (weights / "best.json").write_text("{}", encoding="utf-8")
                (weights / "last.json").write_text("{}", encoding="utf-8")
                (weights / "model_metadata.json").write_text(json.dumps({"backend": "sklearn_xgboost"}), encoding="utf-8")
                (run_dir / "metrics.json").write_text(json.dumps(fake_metrics), encoding="utf-8")
                (run_dir / "results.csv").write_text("epoch,train/loss,val/loss,val/macro_f1\n3,0.1,0.2,1.0\n", encoding="utf-8")
                if progress_callback:
                    progress_callback(fake_metrics["history"][-1])
                return fake_metrics

            with patch("src.training.backends.xgboost_backend.ProjectManager.save_project"), patch(
                "src.training.backends.xgboost_backend.train_xgboost_from_dataset",
                side_effect=fake_train,
            ):
                backend._run_training(project)

            run_dir = root / "training" / "runs" / "run_xgb_unit"
            self.assertTrue(run_dir.joinpath("backend.json").exists())
            self.assertTrue(run_dir.joinpath("metric_schema.json").exists())
            self.assertTrue(run_dir.joinpath("artifact_manifest.json").exists())
            self.assertTrue(run_dir.joinpath("weights", "best.json").exists())
            self.assertTrue(run_dir.joinpath("preprocess", "feature_schema.json").exists())
            backend_contract = json.loads(run_dir.joinpath("backend.json").read_text(encoding="utf-8"))
            self.assertEqual(backend_contract["architecture"], "rnn")
            self.assertEqual(backend_contract["backend"], "sklearn_xgboost")
            summary = json.loads(run_dir.joinpath("run_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["primary_metric_key"], "val/macro_f1")
            self.assertEqual(summary["model"], "xgboost_classifier")
            self.assertEqual(summary["epochs"], 3)
            self.assertEqual(summary["batch_size"], 2)
            artifact_manifest = json.loads(run_dir.joinpath("artifact_manifest.json").read_text(encoding="utf-8"))
            artifact_paths = {item["path"]: item for item in artifact_manifest["artifacts"]}
            self.assertEqual(artifact_paths["weights/best.json"]["role"], "best_model")
            self.assertEqual(artifact_paths["weights/last.json"]["role"], "last_model")
            self.assertEqual(artifact_paths["weights/model_metadata.json"]["type"], "model_metadata")
            self.assertEqual(TrainingStateStore.get_state("proj_xgb")["status"], "completed")


if __name__ == "__main__":
    unittest.main()
