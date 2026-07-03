import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import app


class CNNOutputCompareApiPhase3CTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project_root = self.root / "proj_api_output_compare"
        (self.project_root / "dataset").mkdir(parents=True)
        self.project = {
            "project_id": "proj_api_output_compare",
            "project_name": "api output compare",
            "task_type": "semantic_segmentation",
            "dataset_path": (self.project_root / "dataset").as_posix(),
        }
        self.client = TestClient(app)

    def tearDown(self):
        self.tmp.cleanup()

    def test_output_compare_endpoint_accepts_uploaded_image_and_run_ids(self):
        payload = {
            "comparison_id": "outcmp_test",
            "architecture": "cnn",
            "kind": "image_output",
            "selected_run_ids": ["run_a", "run_b"],
            "outputs": [],
            "summary": {},
            "warnings": [],
        }

        with patch("src.api.routes.training_orchestration.ProjectManager.get_project", return_value=self.project), \
             patch("src.api.routes.training_orchestration.CNNOutputCompareService.compare_image_outputs", return_value=payload) as mocked:
            response = self.client.post(
                "/api/projects/proj_api_output_compare/compare/output-image",
                data={
                    "run_ids_json": '["run_a","run_b"]',
                    "conf": "0.25",
                    "iou": "0.70",
                    "imgsz": "320",
                    "device": "cpu",
                },
                files={"file": ("sample.jpg", b"fake-image", "image/jpeg")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["comparison_id"], "outcmp_test")
        self.assertEqual(mocked.call_args.kwargs["run_ids"], ["run_a", "run_b"])

    def test_output_compare_endpoint_rejects_invalid_run_ids_json(self):
        with patch("src.api.routes.training_orchestration.ProjectManager.get_project", return_value=self.project):
            response = self.client.post(
                "/api/projects/proj_api_output_compare/compare/output-image",
                data={"run_ids_json": "not-json"},
                files={"file": ("sample.jpg", b"fake-image", "image/jpeg")},
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid run_ids_json", response.json()["error"]["message"])


if __name__ == "__main__":
    unittest.main()
