import unittest
from unittest.mock import Mock, patch

from src.training.base_backend import TrainingBackend
from src.training.dispatcher import TrainerDispatcher
from src.training.state_store import TrainingStateStore


class FakeBackend(TrainingBackend):
    backend_name = "fake_backend"
    architecture = "fake_arch"

    def __init__(self):
        self.start_training = Mock(return_value={"status": "started", "run_id": "run_1"})
        self.stop_training = Mock(return_value={"status": "stopping"})
        self.get_status = Mock(return_value={
            "status": "training",
            "epoch": 1,
            "total_epochs": 2,
            "metrics": [],
            "error": "",
            "run_id": "run_1",
            "hardware": {},
        })


class TrainerDispatcherPhase1ATests(unittest.TestCase):
    def setUp(self):
        TrainingStateStore._states.clear()

    def test_default_backend_resolves_to_ultralytics_yolo(self):
        backend = TrainerDispatcher.resolve_backend({})
        self.assertEqual(backend.backend_name, "ultralytics_yolo")
        self.assertEqual(backend.architecture, "cnn")

    def test_unknown_backend_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported training backend"):
            TrainerDispatcher.resolve_backend({"training_config": {"backend": "missing_backend"}})

    def test_dispatcher_status_path_normalizes_backend_status(self):
        fake = FakeBackend()

        with patch.object(TrainerDispatcher, "_backends", {"fake_backend": fake}):
            status = TrainerDispatcher.get_status(
                "project_1",
                {"training_config": {"backend": "fake_backend"}},
            )

        fake.get_status.assert_called_once_with("project_1")
        self.assertEqual(status["status"], "training")
        self.assertEqual(status["architecture"], "fake_arch")
        self.assertEqual(status["backend"], "fake_backend")
        self.assertEqual(TrainingStateStore.get("project_1")["backend"], "fake_backend")

    def test_dispatcher_start_calls_backend_and_updates_state(self):
        fake = FakeBackend()
        project = {
            "project_id": "project_1",
            "training_config": {"backend": "fake_backend", "run_id": "run_1"},
        }

        with patch.object(TrainerDispatcher, "_backends", {"fake_backend": fake}):
            result = TrainerDispatcher.start_training(project)

        fake.start_training.assert_called_once_with(project)
        fake.get_status.assert_called_once_with("project_1")
        self.assertEqual(result["status"], "started")
        self.assertEqual(TrainingStateStore.get("project_1")["run_id"], "run_1")


if __name__ == "__main__":
    unittest.main()
