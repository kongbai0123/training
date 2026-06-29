import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
