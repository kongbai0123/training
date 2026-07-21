import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.project_manager import ProjectManager


class ProjectTaskUpdateTests(unittest.TestCase):
    def test_cnn_task_change_preserves_data_and_history_but_resets_active_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("src.project_manager.PROJECTS_DIR", root):
                project = ProjectManager.create_project("editable", "object_detection", ["defect"])
                project["images"] = [{"filename": "one.jpg", "annotations": [{"category": "defect"}]}]
                project["training_runs"] = [{"run_id": "old_run", "task_type": "object_detection"}]
                project["current"].update({"training_run_id": "old_run", "best_model_id": "old_best", "export_id": "old_export"})
                ProjectManager.save_project(project["project_id"], project)

                result = ProjectManager.update_task_type(project["project_id"], "instance_segmentation")

            saved = json.loads((root / project["project_id"] / "project.json").read_text(encoding="utf-8"))
            self.assertTrue(result["change"]["changed"])
            self.assertEqual(saved["task_type"], "instance_segmentation")
            self.assertEqual(saved["images"], project["images"])
            self.assertEqual(saved["training_runs"], project["training_runs"])
            self.assertEqual(saved["training_config"]["model"], "yolov8n-seg.pt")
            self.assertIsNone(saved["current"]["training_run_id"])
            self.assertIsNone(saved["current"]["best_model_id"])
            self.assertEqual(saved["task_type_history"][-1]["from"], "object_detection")
            self.assertEqual(saved["task_type_history"][-1]["to"], "instance_segmentation")

    def test_switching_to_sequence_regression_sets_rnn_defaults_without_deleting_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("src.project_manager.PROJECTS_DIR", root):
                project = ProjectManager.create_project("editable", "semantic_segmentation", ["road"])
                project["images"] = [{"filename": "road.jpg"}]
                ProjectManager.save_project(project["project_id"], project)
                result = ProjectManager.update_task_type(project["project_id"], "sequence_regression")

            updated = result["project"]
            self.assertEqual(updated["training_config"]["architecture"], "rnn")
            self.assertEqual(updated["training_config"]["task_head"], "regression")
            self.assertEqual(updated["rnn_config"]["task_head"], "regression")
            self.assertEqual(updated["images"], [{"filename": "road.jpg"}])

    def test_rejects_unknown_task_type(self):
        with self.assertRaisesRegex(ValueError, "Unsupported project task type"):
            ProjectManager.update_task_type("missing", "unknown_task")


if __name__ == "__main__":
    unittest.main()
