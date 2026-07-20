import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.project_manager import ProjectManager


class RNNProjectCreationTests(unittest.TestCase):
    def test_sequence_classification_project_uses_rnn_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("src.project_manager.PROJECTS_DIR", root):
                project = ProjectManager.create_project("seq project", "sequence_classification", [])

            project_dir = root / project["project_id"]
            saved = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
            config = saved["training_config"]

            self.assertEqual(saved["task_type"], "sequence_classification")
            self.assertEqual(saved["class_names"], [])
            self.assertEqual(config["architecture"], "rnn")
            self.assertEqual(config["backend"], "pytorch_lstm")
            self.assertEqual(config["model"], "lstm")
            self.assertEqual(config["task_head"], "classification")
            self.assertIn("sequence_length", config)
            self.assertNotIn("imgsz", config)
            self.assertTrue((project_dir / "sequences").exists())

    def test_semantic_segmentation_project_uses_semantic_model_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("src.project_manager.PROJECTS_DIR", root):
                project = ProjectManager.create_project("cnn project", "semantic_segmentation", ["road"])

            config = project["training_config"]

            self.assertEqual(config["architecture"], "cnn")
            self.assertEqual(config["backend"], "pytorch_torchvision")
            self.assertEqual(config["model"], "unet")
            self.assertEqual(config["imgsz"], 640)


if __name__ == "__main__":
    unittest.main()
