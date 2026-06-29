import json
import shutil
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from src.project_data_migration import ProjectDataMigrationTool


class ProjectDataMigrationToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source_root = self.root / "legacy" / "VisionTrainingStudio" / "projects"
        self.target_root = self.root / "app" / "projects"
        self.source_root.mkdir(parents=True)
        self.target_root.mkdir(parents=True)
        self._write_project("proj_legacy_001", "Legacy One")

    def tearDown(self):
        self.tmp.cleanup()

    def test_scan_lists_legacy_projects_and_target_paths(self):
        with self._patched_paths():
            report = ProjectDataMigrationTool.scan()

        self.assertTrue(report["source_exists"])
        self.assertEqual(report["target_root"], self.target_root.resolve().as_posix())
        self.assertEqual(len(report["candidates"]), 1)
        self.assertEqual(report["candidates"][0]["project_id"], "proj_legacy_001")
        self.assertFalse(report["candidates"][0]["target_exists"])

    def test_migrate_copies_without_deleting_source_by_default(self):
        with self._patched_paths():
            result = ProjectDataMigrationTool.migrate(project_ids=["proj_legacy_001"], delete_source=False)

        target_project = self.target_root / "proj_legacy_001"
        source_project = self.source_root / "proj_legacy_001"
        self.assertTrue((target_project / "project.json").exists())
        self.assertTrue(source_project.exists())
        self.assertEqual([item["project_id"] for item in result["migrated"]], ["proj_legacy_001"])
        self.assertEqual(result["deleted"], [])
        self.assertTrue((target_project / "_meta" / "data_root_migration.json").exists())
        copied_project = json.loads((target_project / "project.json").read_text(encoding="utf-8"))
        self.assertEqual(Path(copied_project["dataset_path"]).resolve(), (target_project / "dataset").resolve())

    def test_migrate_deletes_source_only_when_requested(self):
        with self._patched_paths():
            result = ProjectDataMigrationTool.migrate(project_ids=["proj_legacy_001"], delete_source=True)

        self.assertTrue((self.target_root / "proj_legacy_001" / "project.json").exists())
        self.assertFalse((self.source_root / "proj_legacy_001").exists())
        self.assertEqual(result["deleted"], ["proj_legacy_001"])

    def test_existing_target_is_skipped(self):
        shutil.copytree(self.source_root / "proj_legacy_001", self.target_root / "proj_legacy_001")

        with self._patched_paths():
            result = ProjectDataMigrationTool.migrate(project_ids=["proj_legacy_001"], delete_source=True)

        self.assertEqual(result["migrated"], [])
        self.assertEqual(result["deleted"], [])
        self.assertEqual(result["skipped"][0]["reason"], "target_exists")
        self.assertTrue((self.source_root / "proj_legacy_001").exists())

    def _write_project(self, project_id: str, name: str):
        project_dir = self.source_root / project_id
        project_dir.mkdir(parents=True)
        payload = {
            "project_id": project_id,
            "project_name": name,
            "task_type": "semantic_segmentation",
            "created_at": "2026-06-29T00:00:00",
            "updated_at": "2026-06-29T00:01:00",
            "dataset_path": (project_dir / "dataset").resolve().as_posix(),
        }
        (project_dir / "project.json").write_text(json.dumps(payload), encoding="utf-8")
        (project_dir / "dataset").mkdir()
        (project_dir / "dataset" / "sample.txt").write_text("data", encoding="utf-8")

    @contextmanager
    def _patched_paths(self):
        with patch.dict("os.environ", {"VTS_LEGACY_PROJECTS_DIR": str(self.source_root)}, clear=False):
            with patch("src.project_data_migration.PROJECTS_DIR", self.target_root):
                yield


if __name__ == "__main__":
    unittest.main()
