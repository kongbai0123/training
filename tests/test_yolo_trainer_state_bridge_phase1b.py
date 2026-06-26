import unittest
from unittest.mock import patch

from src.trainer import YOLOTrainer
from src.training.state_store import TrainingStateStore


class YOLOTrainerStateBridgePhase1BTests(unittest.TestCase):
    def setUp(self):
        TrainingStateStore._states.clear()
        YOLOTrainer._global_states.clear()
        YOLOTrainer._stop_flags.clear()
        YOLOTrainer._threads.clear()

    def test_stop_training_sets_stop_flag_and_state_store_status(self):
        TrainingStateStore.init_run("project_1", "run_1", 2, "cnn", "ultralytics_yolo")

        YOLOTrainer.stop_training("project_1")

        self.assertTrue(YOLOTrainer._stop_flags["project_1"])
        self.assertEqual(TrainingStateStore.get_state("project_1")["status"], "stopping")
        self.assertEqual(YOLOTrainer._global_states["project_1"]["status"], "stopping")

    def test_get_status_reads_state_store_and_adds_hardware(self):
        TrainingStateStore.init_run("project_1", "run_1", 2, "cnn", "ultralytics_yolo")
        TrainingStateStore.append_epoch_metrics("project_1", {"epoch": 1, "map50": 0.5})

        with patch.object(YOLOTrainer, "get_hardware_info", return_value={"cpu_usage": 1}):
            status = YOLOTrainer.get_status("project_1")

        self.assertEqual(status["status"], "training")
        self.assertEqual(status["epoch"], 1)
        self.assertEqual(status["total_epochs"], 2)
        self.assertEqual(status["run_id"], "run_1")
        self.assertEqual(status["metrics"][0]["map50"], 0.5)
        self.assertEqual(status["hardware"], {"cpu_usage": 1})
        self.assertEqual(status["backend"], "ultralytics_yolo")
        self.assertEqual(status["architecture"], "cnn")

    def test_get_status_falls_back_to_legacy_global_state(self):
        YOLOTrainer._global_states["project_legacy"] = {
            "status": "training",
            "epoch": 1,
            "total_epochs": 2,
            "metrics": [],
            "error": "",
            "run_id": "legacy_run",
        }

        with patch.object(YOLOTrainer, "get_hardware_info", return_value={}):
            status = YOLOTrainer.get_status("project_legacy")

        self.assertEqual(status["run_id"], "legacy_run")
        self.assertEqual(status["status"], "training")


if __name__ == "__main__":
    unittest.main()
