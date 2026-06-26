import unittest
from unittest.mock import patch

from src.training.backends.yolo_backend import YOLOBackend
from src.training.backends.yolo_training_service import YOLOTrainingService


class YOLOBackendContractPhase1DTests(unittest.TestCase):
    def test_validate_readiness_delegates_to_existing_readiness_checker(self):
        backend = YOLOBackend()
        project = {"project_id": "project_1"}
        config = {"model": "yolov8n.pt"}

        with patch(
            "src.training.backends.yolo_training_service.validate_training_readiness",
            return_value=["missing split"],
        ) as readiness_mock:
            errors = backend.validate_readiness(project, config)

        readiness_mock.assert_called_once_with(project, config)
        self.assertEqual(errors, ["missing split"])

    def test_prepare_dataset_delegates_to_existing_yolo_trainer_method(self):
        backend = YOLOBackend()
        project = {"project_id": "project_1"}

        with patch(
            "src.training.backends.yolo_training_service.YOLOTrainer.prepare_yolo_dataset",
            return_value="prepared/data.yaml",
        ) as prepare_mock:
            data_yaml = backend.prepare_dataset(project)

        prepare_mock.assert_called_once_with(project)
        self.assertEqual(data_yaml, "prepared/data.yaml")

    def test_yolo_training_service_is_wrapper_only_for_readiness(self):
        project = {"project_id": "project_1"}
        config = {"model": "yolov8n.pt"}

        with patch(
            "src.training.backends.yolo_training_service.validate_training_readiness",
            return_value=[],
        ) as readiness_mock:
            errors = YOLOTrainingService.validate_readiness(project, config)

        readiness_mock.assert_called_once_with(project, config)
        self.assertEqual(errors, [])

    def test_yolo_training_service_is_wrapper_only_for_prepare_dataset(self):
        project = {"project_id": "project_1"}

        with patch(
            "src.training.backends.yolo_training_service.YOLOTrainer.prepare_yolo_dataset",
            return_value="prepared/data.yaml",
        ) as prepare_mock:
            data_yaml = YOLOTrainingService.prepare_dataset(project)

        prepare_mock.assert_called_once_with(project)
        self.assertEqual(data_yaml, "prepared/data.yaml")


if __name__ == "__main__":
    unittest.main()
