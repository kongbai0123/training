import unittest
from unittest.mock import patch

from src.training.dispatcher import TrainerDispatcher
from src.training.state_store import TrainingStateStore


class DispatcherStatusPhase1BTests(unittest.TestCase):
    def setUp(self):
        TrainingStateStore._states.clear()

    def test_dispatcher_status_remains_frontend_compatible(self):
        raw_status = {
            "status": "training",
            "epoch": 1,
            "total_epochs": 2,
            "metrics": [{"epoch": 1}],
            "error": "",
            "run_id": "run_1",
            "hardware": {"gpu": {"available": True}},
        }

        with patch("src.training.backends.yolo_backend.YOLOTrainer.get_status", return_value=raw_status):
            status = TrainerDispatcher.get_status("project_1", {})

        for key in ["status", "epoch", "total_epochs", "metrics", "error", "run_id", "hardware"]:
            self.assertIn(key, status)
        self.assertEqual(status["backend"], "ultralytics_yolo")
        self.assertEqual(status["architecture"], "cnn")
        self.assertEqual(TrainingStateStore.get_state("project_1")["run_id"], "run_1")


if __name__ == "__main__":
    unittest.main()
