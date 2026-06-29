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


if __name__ == "__main__":
    unittest.main()
