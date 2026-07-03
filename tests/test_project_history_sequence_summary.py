import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.project_manager import ProjectManager


class ProjectHistorySequenceSummaryTests(unittest.TestCase):
    def test_file_summary_reports_sequence_manifest_and_csv_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            sequences_dir = project_dir / "sequences"
            sequences_dir.mkdir(parents=True)
            (sequences_dir / "sequence_manifest.json").write_text('{"sequences": []}', encoding="utf-8")
            (sequences_dir / "features.csv").write_text(
                "sequence_id,timestep,feature_1,label\nseq_1,0,0.1,normal\n",
                encoding="utf-8",
            )

            summary = ProjectManager.build_project_file_summary(project_dir, {"layout": {"mode": "v3"}})

            self.assertTrue(summary["sequence_manifest"])
            self.assertEqual(summary["sequence_csv_files"], 1)
            self.assertGreaterEqual(summary["sequence_files"], 2)

    def test_file_summary_defaults_sequence_sources_to_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = ProjectManager.build_project_file_summary(Path(tmp), {"layout": {"mode": "v3"}})

            self.assertFalse(summary["sequence_manifest"])
            self.assertEqual(summary["sequence_csv_files"], 0)
            self.assertEqual(summary["sequence_files"], 0)

    def test_file_summary_reports_compare_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            report_dir = project_dir / "exports" / "compare_reports" / "compare_cnn_001"
            report_dir.mkdir(parents=True)
            (report_dir / "report.md").write_text("# report\n", encoding="utf-8")

            summary = ProjectManager.build_project_file_summary(project_dir, {"layout": {"mode": "v3"}})

            self.assertEqual(summary["compare_reports"], 1)

    def test_project_history_records_include_name_and_copyable_full_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects_root = Path(tmp)
            project_dir = projects_root / "proj_history"
            project_dir.mkdir(parents=True)
            (project_dir / "project.json").write_text(
                """
                {
                  "project_id": "proj_history",
                  "project_name": "History Project",
                  "task_type": "semantic_segmentation",
                  "created_at": "2026-01-01T00:00:00",
                  "updated_at": "2026-01-02T00:00:00",
                  "class_names": ["part"],
                  "annotation_progress": {"total": 1, "annotated": 0},
                  "layout": {"mode": "v3"}
                }
                """,
                encoding="utf-8",
            )

            with patch("src.project_manager.PROJECTS_DIR", projects_root):
                projects = ProjectManager.get_all_projects()

            self.assertEqual(len(projects), 1)
            record = projects[0]
            expected_path = project_dir.resolve().as_posix()
            self.assertEqual(record["project_name"], "History Project")
            self.assertEqual(record["full_path"], expected_path)
            self.assertEqual(record["copy_path"], expected_path)
            self.assertEqual(record["path"], expected_path)
            self.assertEqual(record["file_summary"]["project_root"], expected_path)


if __name__ == "__main__":
    unittest.main()
