import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import app
from src.local_session import get_session
from src.training.compare_service import CompareService

from test_compare_service_phase3a import make_project, write_yolo_run


class CompareReportPhase3FTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = make_project(self.root)
        write_yolo_run(self.project, "run_a")
        write_yolo_run(self.project, "run_b")
        self.client = TestClient(app)

    def tearDown(self):
        self.tmp.cleanup()

    def test_export_report_writes_json_markdown_and_csv(self):
        payload = CompareService.export_report(self.project, "cnn", ["run_a", "run_b"], "run_a")

        report_dir = Path(payload["report_dir"])
        self.assertTrue(report_dir.joinpath("report.json").exists())
        self.assertTrue(report_dir.joinpath("report.md").exists())
        self.assertTrue(report_dir.joinpath("summary.csv").exists())
        self.assertTrue(report_dir.joinpath("report.pdf").exists())
        self.assertIn("Model Compare Report", report_dir.joinpath("report.md").read_text(encoding="utf-8"))
        self.assertTrue(report_dir.joinpath("report.pdf").read_bytes().startswith(b"%PDF-"))
        self.assertEqual([item["filename"] for item in payload["files"]], ["report.json", "report.md", "summary.csv", "report.pdf"])

    def test_export_report_api_and_download(self):
        with patch("app.ProjectManager.get_project", return_value=self.project):
            response = self.client.post(
                "/api/projects/proj_compare/compare/report",
                json={"architecture": "cnn", "run_ids": ["run_a", "run_b"], "baseline_run_id": "run_a"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["files"]), 4)
        markdown = next(item for item in body["files"] if item["filename"] == "report.md")
        pdf = next(item for item in body["files"] if item["filename"] == "report.pdf")

        with patch("app.ProjectManager.get_project", return_value=self.project):
            download = self.client.get(markdown["url"], headers={"X-VTS-Token": get_session().token})

        self.assertEqual(download.status_code, 200)
        self.assertIn("Model Compare Report", download.text)

        with patch("app.ProjectManager.get_project", return_value=self.project):
            pdf_download = self.client.get(pdf["url"], headers={"X-VTS-Token": get_session().token})

        self.assertEqual(pdf_download.status_code, 200)
        self.assertEqual(pdf_download.headers["content-type"], "application/pdf")
        self.assertTrue(pdf_download.content.startswith(b"%PDF-"))

    def test_list_and_delete_report_api(self):
        exported = CompareService.export_report(self.project, "cnn", ["run_a", "run_b"], "run_a")

        with patch("app.ProjectManager.get_project", return_value=self.project):
            list_response = self.client.get("/api/projects/proj_compare/compare/reports")

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["reports"][0]["report_id"], exported["report_id"])

        with patch("app.ProjectManager.get_project", return_value=self.project):
            delete_response = self.client.delete(f"/api/projects/proj_compare/compare/reports/{exported['report_id']}")

        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(Path(exported["report_dir"]).exists())


if __name__ == "__main__":
    unittest.main()
