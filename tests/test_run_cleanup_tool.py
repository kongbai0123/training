import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import app


def make_cleanup_project(root: Path) -> dict:
    project_dir = root / "proj_cleanup"
    dataset_dir = project_dir / "dataset"
    runs_dir = project_dir / "training" / "runs"
    dataset_dir.mkdir(parents=True)
    for run_id in ("run_smoke_001", "run_real_001"):
        weights_dir = runs_dir / run_id / "weights"
        weights_dir.mkdir(parents=True)
        (weights_dir / "best.pt").write_bytes(b"best")
        (weights_dir / "last.pt").write_bytes(b"last")
        (runs_dir / run_id / "metrics.json").write_text("{}", encoding="utf-8")
    return {
        "project_id": "proj_cleanup",
        "name": "cleanup test",
        "task_type": "semantic_segmentation",
        "dataset_path": str(dataset_dir),
        "current": {
            "training_run_id": "run_smoke_001",
            "best_model_id": "proj_cleanup::run_smoke_001::best",
        },
        "training_runs": [
            {
                "run_id": "run_smoke_001",
                "status": "completed",
                "model": "yolov8s-seg.pt",
                "task_type": "semantic_segmentation",
                "completed_at": "2026-07-01T10:00:00",
            },
            {
                "run_id": "run_real_001",
                "status": "completed",
                "model": "yolov8s-seg.pt",
                "task_type": "semantic_segmentation",
                "completed_at": "2026-07-01T11:00:00",
            },
        ],
    }


class RunCleanupToolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = make_cleanup_project(self.root)
        self.project_dir = Path(self.project["dataset_path"]).parent
        self.client = TestClient(app)

    def tearDown(self):
        self.tmp.cleanup()

    def test_lists_only_test_run_candidates(self):
        with patch("src.api.routes.training_runs.ProjectManager.get_project", return_value=self.project):
            response = self.client.get("/api/projects/proj_cleanup/runs/cleanup-candidates")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["candidates"][0]["run_id"], "run_smoke_001")
        self.assertTrue(body["candidates"][0]["best"]["exists"])
        self.assertTrue(body["candidates"][0]["last"]["exists"])

    def test_cleanup_requires_confirmation(self):
        with patch("src.api.routes.training_runs.ProjectManager.get_project", return_value=self.project):
            response = self.client.post(
                "/api/projects/proj_cleanup/runs/cleanup",
                json={"run_ids": ["run_smoke_001"], "confirm": False},
            )

        self.assertEqual(response.status_code, 400)
        self.assertTrue((self.project_dir / "training" / "runs" / "run_smoke_001").exists())

    def test_cleanup_removes_only_matching_test_run(self):
        saved_projects = []

        def save_project(project_id, project):
            saved_projects.append(project)
            self.project = project
            return True

        def get_project(_project_id):
            return self.project

        with patch("src.api.routes.training_runs.ProjectManager.get_project", side_effect=get_project), patch(
            "src.api.routes.training_runs.ProjectManager.save_project", side_effect=save_project
        ):
            response = self.client.post(
                "/api/projects/proj_cleanup/runs/cleanup",
                json={"run_ids": ["run_smoke_001", "run_real_001"], "confirm": True},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual([item["run_id"] for item in body["deleted"]], ["run_smoke_001"])
        self.assertEqual(body["skipped"], [{"run_id": "run_real_001", "reason": "not_test_candidate"}])
        self.assertFalse((self.project_dir / "training" / "runs" / "run_smoke_001").exists())
        self.assertTrue((self.project_dir / "training" / "runs" / "run_real_001").exists())
        self.assertEqual([run["run_id"] for run in self.project["training_runs"]], ["run_real_001"])
        self.assertIsNone(self.project["current"]["training_run_id"])
        self.assertIsNone(self.project["current"]["best_model_id"])
        self.assertEqual(len(saved_projects), 1)


if __name__ == "__main__":
    unittest.main()
