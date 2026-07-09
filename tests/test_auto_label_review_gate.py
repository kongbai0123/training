import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.auto_label_review_gate import auto_label_training_errors, build_auto_label_review_gate
from src.project_manager import ProjectManager


class AutoLabelReviewGateTest(unittest.TestCase):
    def _project(self, root: Path):
        return {
            "project_id": "proj_gate",
            "project_name": "Gate Test",
            "dataset_path": str((root / "dataset").resolve()),
            "layout": {"mode": "v3"},
        }

    def _write_summary(self, root: Path, items):
        job_dir = root / "auto_labeling" / "jobs" / "al_gate"
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "summary.json").write_text(
            json.dumps({"job_id": "al_gate", "items": items}, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_pending_drafts_block_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_summary(root, [{"filename": "a.png", "review_status": "pending"}])

            gate = build_auto_label_review_gate(self._project(root))

            self.assertTrue(gate["blocked"])
            self.assertEqual(gate["pending"], 1)
            self.assertIn("al_gate", gate["jobs_with_pending"])
            self.assertTrue(auto_label_training_errors(self._project(root)))

    def test_accepted_drafts_do_not_block_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_summary(root, [{"filename": "a.png", "review_status": "accepted"}])

            gate = build_auto_label_review_gate(self._project(root))

            self.assertFalse(gate["blocked"])
            self.assertEqual(gate["accepted"], 1)
            self.assertEqual(auto_label_training_errors(self._project(root)), [])

    def test_unaccepted_current_auto_label_annotation_blocks_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            labelme_dir = root / "annotations" / "current" / "labelme"
            labelme_dir.mkdir(parents=True, exist_ok=True)
            (labelme_dir / "unsafe.json").write_text(
                json.dumps(
                    {
                        "flags": {
                            "auto_label": True,
                            "auto_label_review_status": "pending",
                            "requires_review": True,
                        }
                    }
                ),
                encoding="utf-8",
            )

            gate = build_auto_label_review_gate(self._project(root))

            self.assertTrue(gate["blocked"])
            self.assertEqual(gate["unsafe_current"], ["unsafe.json"])
            self.assertTrue(auto_label_training_errors(self._project(root)))

    def test_project_manager_exposes_gate_without_persisting_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir = Path(tmp)
            project_dir = projects_dir / "proj_gate"
            project_dir.mkdir(parents=True, exist_ok=True)
            project = self._project(project_dir)
            project.update(
                {
                    "project_id": "proj_gate",
                    "project_name": "Gate Test",
                    "task_type": "object_detection",
                    "class_names": ["defect"],
                    "images": [],
                }
            )
            (project_dir / "project.json").write_text(json.dumps(project), encoding="utf-8")
            self._write_summary(project_dir, [{"filename": "a.png", "review_status": "pending"}])

            with patch("src.project_manager.PROJECTS_DIR", projects_dir):
                loaded = ProjectManager.get_project("proj_gate")
                self.assertTrue(loaded["auto_label_review_gate"]["blocked"])
                self.assertEqual(loaded["auto_label_review_gate"]["pending"], 1)
                ProjectManager.save_project("proj_gate", loaded)

            saved = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
            self.assertNotIn("auto_label_review_gate", saved)


if __name__ == "__main__":
    unittest.main()
