import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.training.base_backend import TrainingBackend
from src.training.dispatcher import TrainerDispatcher
from src.training.start_service import TrainingReadinessError, TrainingRunAlreadyExists, TrainingStartService


class FakeStartBackend(TrainingBackend):
    backend_name = "fake_start"
    architecture = "fake_arch"

    def __init__(self, readiness_errors=None):
        self.readiness_errors = readiness_errors or []
        self.validate_readiness = Mock(side_effect=lambda project, config: self.readiness_errors)
        self.start_training = Mock(return_value={"status": "started"})
        self.get_status = Mock(return_value={
            "status": "training",
            "epoch": 0,
            "total_epochs": 1,
            "metrics": [],
            "error": "",
            "run_id": "run_a",
            "hardware": {},
        })


class TrainingStartServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project_dir = Path(self.tmp.name) / "proj_start"
        (self.project_dir / "dataset").mkdir(parents=True)
        self.project = {
            "project_id": "proj_start",
            "dataset_path": (self.project_dir / "dataset").as_posix(),
        }
        self.config = {
            "model": "yolov8n.pt",
            "epochs": 1,
            "batch_size": 2,
            "imgsz": 320,
            "lr0": 0.01,
            "device": "cpu",
            "patience": 5,
            "workers": 1,
            "cache": False,
            "amp": True,
            "seed": 42,
            "save_period": 1,
            "close_mosaic": 0,
            "optimizer": "auto",
            "run_id": "run_a",
            "backend": "fake_start",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_start_writes_training_config_and_dispatches_backend(self):
        fake = FakeStartBackend()
        self.config.update({
            "gradient_clip_norm": 1.0,
            "early_stopping_patience": 7,
        })

        with patch.object(TrainerDispatcher, "_backends", {"fake_start": fake}), \
             patch("src.training.start_service.ProjectManager.save_project", return_value=True) as save_project:
            payload = TrainingStartService.start("proj_start", self.project, self.config)

        self.assertEqual(payload, {"status": "started", "message": "Training started.", "run_id": "run_a"})
        self.assertEqual(self.project["training_config"]["run_id"], "run_a")
        self.assertEqual(self.project["training_config"]["backend"], "fake_start")
        self.assertEqual(self.project["training_config"]["gradient_clip_norm"], 1.0)
        self.assertEqual(self.project["training_config"]["early_stopping_patience"], 7)
        fake.validate_readiness.assert_called_once()
        fake.start_training.assert_called_once_with(self.project)
        save_project.assert_called_once()

    def test_start_raises_readiness_error_before_save(self):
        fake = FakeStartBackend(["missing dataset"])

        with patch.object(TrainerDispatcher, "_backends", {"fake_start": fake}), \
             patch("src.training.start_service.ProjectManager.save_project") as save_project:
            with self.assertRaisesRegex(TrainingReadinessError, "missing dataset"):
                TrainingStartService.start("proj_start", self.project, self.config)

        save_project.assert_not_called()
        fake.start_training.assert_not_called()

    def test_start_rejects_duplicate_run_id(self):
        run_dir = self.project_dir / "training" / "runs" / "run_a"
        run_dir.mkdir(parents=True)
        fake = FakeStartBackend()

        with patch.object(TrainerDispatcher, "_backends", {"fake_start": fake}), \
             patch("src.training.start_service.ProjectManager.save_project") as save_project:
            with self.assertRaisesRegex(TrainingRunAlreadyExists, "already exists"):
                TrainingStartService.start("proj_start", self.project, self.config)

        save_project.assert_not_called()
        fake.start_training.assert_not_called()


if __name__ == "__main__":
    unittest.main()
