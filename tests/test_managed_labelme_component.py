import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import app
from src.api.routes.annotation_labelme import build_labelme_open_command
from src.annotation_helpers import find_labelme_executable
from src.managed_labelme import get_labelme_component_status, install_labelme_component_archive


def _build_component_archive(root: Path, *, checksum: str | None = None) -> Path:
    executable = b"standalone-labelme-exe"
    digest = checksum or hashlib.sha256(executable).hexdigest()
    manifest = {
        "component_id": "labelme",
        "version": "6.3.1",
        "platforms": ["windows-x64"],
        "entrypoint": "LabelMe/LabelMe.exe",
        "sha256": {"LabelMe/LabelMe.exe": digest},
    }
    archive = root / "labelme.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("component.json", json.dumps(manifest))
        output.writestr("LabelMe/LabelMe.exe", executable)
    return archive


class ManagedLabelMeComponentTests(unittest.TestCase):
    def test_component_installs_and_reports_offline_ready(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            component_dir = root / "components" / "labelme"
            temp_root = root / "tmp"
            temp_root.mkdir()
            archive = _build_component_archive(root)
            with patch("src.managed_labelme.LABELME_COMPONENT_DIR", component_dir), patch("src.managed_labelme.TMP_DIR", temp_root):
                status = install_labelme_component_archive(archive)

            self.assertEqual(status["runtime_mode"], "managed")
            self.assertTrue(status["offline_ready"])
            self.assertEqual(status["version"], "6.3.1")
            self.assertTrue((component_dir / "LabelMe" / "LabelMe.exe").is_file())

    def test_component_rejects_checksum_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            temp_root = root / "tmp"
            temp_root.mkdir()
            archive = _build_component_archive(root, checksum="0" * 64)
            with patch("src.managed_labelme.LABELME_COMPONENT_DIR", root / "components" / "labelme"), patch("src.managed_labelme.TMP_DIR", temp_root):
                with self.assertRaisesRegex(ValueError, "checksum"):
                    install_labelme_component_archive(archive)

    def test_component_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("../escape.exe", b"unsafe")
            temp_root = root / "tmp"
            temp_root.mkdir()
            with patch("src.managed_labelme.LABELME_COMPONENT_DIR", root / "components" / "labelme"), patch("src.managed_labelme.TMP_DIR", temp_root):
                with self.assertRaisesRegex(ValueError, "safe"):
                    install_labelme_component_archive(archive)

    def test_managed_executable_has_priority(self):
        with patch("src.annotation_helpers.get_managed_labelme_executable", return_value="C:/managed/LabelMe.exe"), patch("src.annotation_helpers.shutil.which", return_value="C:/system/labelme.exe"):
            self.assertEqual(find_labelme_executable(), "C:/managed/LabelMe.exe")

    def test_no_executable_produces_no_launch_command(self):
        command = build_labelme_open_command(None, Path("images"), Path("labels"), [])
        self.assertEqual(command, [])

    def test_status_does_not_depend_on_development_agent_path(self):
        source = (Path(__file__).resolve().parents[1] / "src" / "annotation_helpers.py").read_text(encoding="utf-8")
        self.assertNotIn("hermes-agent", source)


class ManagedLabelMeApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_status_endpoint_is_project_independent(self):
        response = self.client.get("/api/components/labelme")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["component_id"], "labelme")

    def test_upload_install_requires_confirmation(self):
        response = self.client.post(
            "/api/components/labelme/install",
            data={"confirm": "false"},
            files={"file": ("labelme.zip", b"not-used", "application/zip")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("explicit confirmation", response.json()["error"]["message"])


if __name__ == "__main__":
    unittest.main()
