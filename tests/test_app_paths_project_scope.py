import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import src.app_paths as app_paths


class AppPathsProjectScopeTests(unittest.TestCase):
    def tearDown(self):
        importlib.reload(app_paths)

    def test_default_projects_dir_stays_under_app_home(self):
        with patch.dict("os.environ", {"VTS_USER_DATA_DIR": "", "VTS_PROJECTS_DIR": ""}, clear=False):
            reloaded = importlib.reload(app_paths)

        self.assertEqual(reloaded.USER_DATA_DIR, reloaded.APP_HOME)
        self.assertEqual(reloaded.PROJECTS_DIR, reloaded.APP_HOME / "projects")
        self.assertTrue(reloaded.PROJECTS_DIR.exists())

    def test_explicit_projects_dir_override_is_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "managed_projects"
            with patch.dict("os.environ", {"VTS_PROJECTS_DIR": str(target)}, clear=False):
                reloaded = importlib.reload(app_paths)

            self.assertEqual(reloaded.PROJECTS_DIR, target.resolve())
            self.assertTrue(reloaded.PROJECTS_DIR.exists())

    def test_frozen_paths_prefer_managed_portable_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe_dir = root / "dist" / "VisionTrainingStudio"
            exe_dir.mkdir(parents=True)
            (root / "version.json").write_text("{}", encoding="utf-8")
            managed_projects = root / "projects"
            managed_projects.mkdir()
            managed_models = root / "models"
            fake_exe = exe_dir / "VisionTrainingStudio.exe"
            fake_exe.write_bytes(b"")

            with patch.dict("os.environ", {"VTS_USER_DATA_DIR": "", "VTS_PROJECTS_DIR": ""}, clear=False), patch.object(app_paths.sys, "frozen", True, create=True), patch.object(app_paths.sys, "executable", str(fake_exe)):
                reloaded = importlib.reload(app_paths)

            self.assertEqual(reloaded.USER_DATA_DIR, root.resolve())
            self.assertEqual(reloaded.PROJECTS_DIR, managed_projects.resolve())
            self.assertEqual(reloaded.MODELS_DIR, managed_models.resolve())


if __name__ == "__main__":
    unittest.main()
