import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.training.export_service import ExportService, ExportableModelNotFound


class FakeYOLO:
    def __init__(self, weight_path: str):
        self.weight_path = Path(weight_path)

    def export(self, format: str):
        if format != "onnx":
            raise ValueError("unexpected export format")
        self.weight_path.with_suffix(".onnx").write_bytes(b"fake-onnx")


class ExportServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project_dir = self.root / "proj_export"
        (self.project_dir / "dataset").mkdir(parents=True)
        self.project = {
            "project_id": "proj_export",
            "project_name": "export",
            "dataset_path": (self.project_dir / "dataset").as_posix(),
            "training_runs": [{"run_id": "run_a", "status": "completed", "timestamp": "2026-01-01T00:00:00"}],
        }
        self.best_pt = self.project_dir / "training" / "runs" / "run_a" / "weights" / "best.pt"
        self.best_pt.parent.mkdir(parents=True, exist_ok=True)
        self.best_pt.write_bytes(b"fake-pt")

    def tearDown(self):
        self.tmp.cleanup()

    def test_resolve_exportable_weight_prefers_explicit_run(self):
        resolved = ExportService.resolve_exportable_weight(self.project, run_id="run_a")

        self.assertEqual(resolved, self.best_pt)

    def test_export_project_model_writes_export_summary_and_updates_current(self):
        with patch("src.training.export_service.YOLO", FakeYOLO), \
             patch("src.training.export_service.ProjectManager.save_project", return_value=True) as save_project:
            payload = ExportService.export_project_model("proj_export", self.project, run_id="run_a")

        self.assertTrue(payload["success"])
        self.assertTrue(Path(payload["pt_path"]).exists())
        self.assertTrue(Path(payload["onnx_path"]).exists())
        self.assertEqual(Path(payload["onnx_path"]).read_bytes(), b"fake-onnx")
        self.assertEqual(self.project["current"]["export_id"], payload["export_id"])
        save_project.assert_called_once()

    def test_export_run_onnx_requires_best_weight(self):
        self.best_pt.unlink()

        with self.assertRaisesRegex(ExportableModelNotFound, "best.pt not found"):
            ExportService.export_run_onnx("proj_export", self.project, "run_a")


if __name__ == "__main__":
    unittest.main()
