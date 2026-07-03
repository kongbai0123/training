import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import app

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_compare_service_phase3e_rnn import make_rnn_project, write_rnn_run


class CompareApiPhase3ERNNTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = make_rnn_project(self.root)
        write_rnn_run(self.project, "run_rnn_a")
        write_rnn_run(self.project, "run_rnn_b")
        self.client = TestClient(app)

    def tearDown(self):
        self.tmp.cleanup()

    def test_list_rnn_compare_runs_endpoint(self):
        with patch("src.api.routes.training_orchestration.ProjectManager.get_project", return_value=self.project):
            response = self.client.get("/api/projects/proj_rnn_compare/compare/runs?architecture=rnn")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["architecture"], "rnn")
        self.assertEqual([run["run_id"] for run in body["runs"]], ["run_rnn_a", "run_rnn_b"])

    def test_compare_rnn_endpoint(self):
        with patch("src.api.routes.training_orchestration.ProjectManager.get_project", return_value=self.project):
            response = self.client.post(
                "/api/projects/proj_rnn_compare/compare",
                json={
                    "architecture": "rnn",
                    "run_ids": ["run_rnn_a", "run_rnn_b"],
                    "baseline_run_id": "run_rnn_a",
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["architecture"], "rnn")
        self.assertEqual(body["task_family"], "classification")
        self.assertIn("val/macro_f1", body["series"])
        self.assertIn("recommendation", body)


if __name__ == "__main__":
    unittest.main()
