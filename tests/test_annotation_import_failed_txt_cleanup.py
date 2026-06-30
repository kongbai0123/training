import json
import tempfile
import unittest
from pathlib import Path

from src.annotation_importer import AnnotationImporter


class AnnotationImportFailedTxtCleanupTests(unittest.TestCase):
    def _project(self, root: Path):
        dataset = root / "dataset"
        (dataset / "images" / "raw").mkdir(parents=True, exist_ok=True)
        return {
            "project_id": "proj_test",
            "project_name": "test",
            "dataset_path": dataset.as_posix(),
            "layout": {"mode": "v3", "version": "v3"},
            "class_names": ["road"],
        }

    def _write_report(self, root: Path, import_id: str):
        source = root / "annotations" / "drafts" / "import" / import_id / "source"
        source.mkdir(parents=True, exist_ok=True)
        (source / "orphan.txt").write_text("0 0.5 0.5 0.1 0.1\n", encoding="utf-8")
        (source / "bad.txt").write_text("bad\n", encoding="utf-8")
        report = {
            "import_id": import_id,
            "total_files": 2,
            "yolo_txt": 2,
            "converted": 0,
            "failed": 2,
            "errors": [
                {"file": "orphan.txt", "message": "Image file not found for orphan."},
                {"file": "bad.txt", "message": "No valid YOLO annotations found."},
            ],
            "warnings": [],
            "converted_files": [],
        }
        report_path = root / "annotations" / "drafts" / "import" / import_id / "import_report.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")

    def test_delete_failed_missing_image_txt_updates_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._project(root)
            import_id = "imp_test"
            self._write_report(root, import_id)

            result = AnnotationImporter.delete_failed_source_file(project, import_id, "orphan.txt")

            self.assertTrue(result["deleted"])
            self.assertFalse((root / "annotations" / "drafts" / "import" / import_id / "source" / "orphan.txt").exists())
            self.assertEqual(result["report"]["failed"], 1)
            self.assertEqual(result["report"]["yolo_txt"], 1)
            self.assertEqual(result["report"]["total_files"], 1)
            self.assertEqual([item["file"] for item in result["report"]["errors"]], ["bad.txt"])
            self.assertEqual(result["report"]["deleted_source_files"][0]["file"], "orphan.txt")

    def test_delete_rejects_non_missing_image_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._project(root)
            import_id = "imp_test"
            self._write_report(root, import_id)

            with self.assertRaises(ValueError):
                AnnotationImporter.delete_failed_source_file(project, import_id, "bad.txt")

            self.assertTrue((root / "annotations" / "drafts" / "import" / import_id / "source" / "bad.txt").exists())


if __name__ == "__main__":
    unittest.main()
