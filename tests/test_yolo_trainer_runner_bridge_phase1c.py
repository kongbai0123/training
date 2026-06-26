import unittest
from unittest.mock import MagicMock, patch

from src.trainer import YOLOTrainer
from src.training.state_store import TrainingStateStore


class YOLOTrainerRunnerBridgePhase1CTests(unittest.TestCase):
    def setUp(self):
        TrainingStateStore._states.clear()
        YOLOTrainer._global_states.clear()
        YOLOTrainer._stop_flags.clear()
        YOLOTrainer._threads.clear()

    def test_start_training_uses_runner_start(self):
        project = {
            "project_id": "project_1",
            "training_config": {"run_id": "run_1"},
        }
        runner = MagicMock()
        runner.is_running.return_value = False
        runner.start.return_value = {
            "started": True,
            "project_id": "project_1",
            "run_id": "run_1",
            "thread_name": "training-project_1-run_1",
        }

        with patch("src.trainer.DEFAULT_THREAD_TRAINING_RUNNER", runner):
            YOLOTrainer.start_training(project)

        runner.start.assert_called_once()
        call_kwargs = runner.start.call_args.kwargs
        self.assertEqual(call_kwargs["project_id"], "project_1")
        self.assertEqual(call_kwargs["run_id"], "run_1")
        self.assertEqual(call_kwargs["target"], YOLOTrainer._run_yolo)
        self.assertEqual(call_kwargs["args"], (project,))
        self.assertFalse(call_kwargs["daemon"])
        self.assertEqual(YOLOTrainer._threads["project_1"]["run_id"], "run_1")

    def test_runner_duplicate_prevents_second_start(self):
        project = {"project_id": "project_1", "training_config": {"run_id": "run_1"}}
        runner = MagicMock()
        runner.is_running.return_value = True

        with patch("src.trainer.DEFAULT_THREAD_TRAINING_RUNNER", runner):
            YOLOTrainer.start_training(project)

        runner.start.assert_not_called()
        self.assertNotIn("project_1", YOLOTrainer._threads)

    def test_stale_training_state_prevents_start_without_runner(self):
        TrainingStateStore.init_run("project_1", "run_1", 2, "cnn", "ultralytics_yolo")
        project = {"project_id": "project_1", "training_config": {"run_id": "run_2"}}
        runner = MagicMock()
        runner.is_running.return_value = False

        with patch("src.trainer.DEFAULT_THREAD_TRAINING_RUNNER", runner):
            YOLOTrainer.start_training(project)

        runner.start.assert_not_called()
        self.assertNotIn("project_1", YOLOTrainer._threads)

    def test_stop_training_keeps_stop_flag_ownership_and_does_not_cleanup_runner(self):
        TrainingStateStore.init_run("project_1", "run_1", 2, "cnn", "ultralytics_yolo")
        runner = MagicMock()

        with patch("src.trainer.DEFAULT_THREAD_TRAINING_RUNNER", runner):
            YOLOTrainer.stop_training("project_1")

        self.assertTrue(YOLOTrainer._stop_flags["project_1"])
        self.assertEqual(TrainingStateStore.get_state("project_1")["status"], "stopping")
        runner.cleanup.assert_not_called()

    def test_get_status_remains_frontend_compatible(self):
        TrainingStateStore.init_run("project_1", "run_1", 2, "cnn", "ultralytics_yolo")

        with patch.object(YOLOTrainer, "get_hardware_info", return_value={"cpu_usage": 1}):
            status = YOLOTrainer.get_status("project_1")

        for key in ["status", "epoch", "total_epochs", "metrics", "error", "run_id", "hardware"]:
            self.assertIn(key, status)
        self.assertEqual(status["hardware"], {"cpu_usage": 1})


if __name__ == "__main__":
    unittest.main()
