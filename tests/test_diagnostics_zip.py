import tempfile
import unittest
import zipfile
from pathlib import Path

from src.diagnostics import SENSITIVE_EXTENSIONS, generate_diagnostics_zip


class DiagnosticsZipTests(unittest.TestCase):
    def test_diagnostics_zip_contains_safe_reports_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = generate_diagnostics_zip(Path(tmp))

            self.assertTrue(zip_path.exists())
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = set(zf.namelist())

            self.assertIn("diagnostics.json", names)
            self.assertIn("health.json", names)
            self.assertIn("project_summary.json", names)
            self.assertIn("exclusions.json", names)
            self.assertIn("version.json", names)

            sensitive = [name for name in names if Path(name).suffix.lower() in SENSITIVE_EXTENSIONS]
            self.assertEqual([], sensitive)


if __name__ == "__main__":
    unittest.main()
