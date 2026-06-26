import unittest
from unittest.mock import patch

from src.training.backends.yolo_backend import YOLOBackend


class YOLOBackendWrapperPhase1ATests(unittest.TestCase):
    def test_start_training_delegates_to_yolo_trainer(self):
        backend = YOLOBackend()
        project = {"project_id": "project_1", "training_config": {"run_id": "run_1"}}

        with patch("src.training.backends.yolo_backend.YOLOTrainer.start_training") as start_mock:
            result = backend.start_training(project)

        start_mock.assert_called_once_with(project)
        self.assertEqual(result["status"], "started")
        self.assertEqual(result["backend"], "ultralytics_yolo")
        self.assertEqual(result["architecture"], "cnn")
        self.assertEqual(result["run_id"], "run_1")

    def test_stop_training_delegates_to_yolo_trainer(self):
        backend = YOLOBackend()

        with patch("src.training.backends.yolo_backend.YOLOTrainer.stop_training") as stop_mock:
            result = backend.stop_training("project_1")

        stop_mock.assert_called_once_with("project_1")
        self.assertEqual(result["status"], "stopping")
        self.assertEqual(result["backend"], "ultralytics_yolo")

    def test_get_status_preserves_existing_fields_and_adds_backend_fields(self):
        backend = YOLOBackend()
        raw_status = {
            "status": "training",
            "epoch": 1,
            "total_epochs": 2,
            "metrics": [],
            "error": "",
            "run_id": "run_1",
            "hardware": {"cpu_usage": 10},
        }

        with patch("src.training.backends.yolo_backend.YOLOTrainer.get_status", return_value=raw_status):
            status = backend.get_status("project_1")

        self.assertEqual(status["status"], "training")
        self.assertEqual(status["epoch"], 1)
        self.assertEqual(status["run_id"], "run_1")
        self.assertEqual(status["backend"], "ultralytics_yolo")
        self.assertEqual(status["architecture"], "cnn")

    def test_contract_methods_exist_without_changing_training_methods(self):
        backend = YOLOBackend()

        self.assertTrue(callable(backend.validate_readiness))
        self.assertTrue(callable(backend.prepare_dataset))


if __name__ == "__main__":
    unittest.main()
