import unittest
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import app

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_compare_service_phase3a import make_project, write_yolo_run


class CompareApiPhase3ATest(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path

        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = make_project(self.root)
        write_yolo_run(self.project, "run_a")
        write_yolo_run(self.project, "run_b")
        self.client = TestClient(app)

    def tearDown(self):
        self.tmp.cleanup()

    def test_list_compare_runs_endpoint(self):
        with patch("src.api.routes.training_orchestration.ProjectManager.get_project", return_value=self.project):
            response = self.client.get("/api/projects/proj_compare/compare/runs?architecture=cnn")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["architecture"], "cnn")
        self.assertEqual([run["run_id"] for run in body["runs"]], ["run_a", "run_b"])

    def test_compare_endpoint(self):
        with patch("src.api.routes.training_orchestration.ProjectManager.get_project", return_value=self.project):
            response = self.client.post(
                "/api/projects/proj_compare/compare",
                json={
                    "architecture": "cnn",
                    "run_ids": ["run_a", "run_b"],
                    "baseline_run_id": "run_a",
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["comparison_id"], "temp")
        self.assertEqual(body["baseline_run_id"], "run_a")
        self.assertEqual(len(body["selected_runs"]), 2)
        self.assertIn("recommendation", body)

    def test_compare_endpoint_rejects_invalid_request(self):
        with patch("src.api.routes.training_orchestration.ProjectManager.get_project", return_value=self.project):
            response = self.client.post(
                "/api/projects/proj_compare/compare",
                json={"architecture": "cnn", "run_ids": ["run_a"]},
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("at least 2", response.json()["error"]["message"])


if __name__ == "__main__":
    unittest.main()
