import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.package_portable import build_portable_archive


class PortablePackagerTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, Path]:
        dist = root / "dist" / "VisionTrainingStudio"
        (dist / "_internal").mkdir(parents=True)
        (dist / "VisionTrainingStudio.exe").write_bytes(b"packaged-executable")
        (dist / "_internal" / "runtime.dll").write_bytes(b"runtime")
        version_file = root / "version.json"
        version_file.write_text(
            json.dumps({"product": "Vision Training Studio", "version": "0.1.0", "build": "test"}),
            encoding="utf-8",
        )
        return dist, version_file

    def test_archive_contains_explicit_portable_marker_and_no_user_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dist, version_file = self._fixture(root)
            output = root / "portable.zip"

            result = build_portable_archive(dist, output, version_file)

            self.assertEqual(result["mode"], "portable")
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertIn("VisionTrainingStudio/portable.mode", names)
                self.assertIn("VisionTrainingStudio/portable_manifest.json", names)
                self.assertIn("VisionTrainingStudio/VisionTrainingStudio.exe", names)
                self.assertFalse(any(name.startswith("VisionTrainingStudio/projects/") for name in names))
                self.assertIsNone(archive.testzip())

    def test_packager_rejects_dist_with_user_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dist, version_file = self._fixture(root)
            (dist / "logs").mkdir()
            (dist / "logs" / "app.log").write_text("should not ship", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "factory clean"):
                build_portable_archive(dist, root / "portable.zip", version_file)


if __name__ == "__main__":
    unittest.main()
