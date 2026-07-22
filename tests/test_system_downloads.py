import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import app
from src.system_downloads import copy_file_to_downloads, safe_download_filename, save_bytes_to_downloads


class SystemDownloadsTests(unittest.TestCase):
    def test_downloads_are_saved_outside_appdata_and_collisions_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            downloads = Path(tmp) / "Downloads"
            with patch("src.system_downloads.resolve_downloads_dir", return_value=downloads):
                first = save_bytes_to_downloads(b"first", "metrics.svg")
                second = save_bytes_to_downloads(b"second", "metrics.svg")

            self.assertEqual(first.parent, downloads)
            self.assertEqual(second.parent, downloads)
            self.assertEqual(first.name, "metrics.svg")
            self.assertEqual(second.name, "metrics (1).svg")
            self.assertEqual(first.read_bytes(), b"first")
            self.assertEqual(second.read_bytes(), b"second")
            self.assertEqual(first.parent.name, "Downloads")

    def test_copy_download_sanitizes_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.svg"
            source.write_text("<svg/>", encoding="utf-8")
            downloads = root / "Downloads"
            with patch("src.system_downloads.resolve_downloads_dir", return_value=downloads):
                destination = copy_file_to_downloads(source, "bad:name.svg")

            self.assertEqual(destination.name, "bad_name.svg")
            self.assertEqual(destination.read_text(encoding="utf-8"), "<svg/>")
            self.assertEqual(safe_download_filename("../report.svg"), "report.svg")

    def test_text_download_api_accepts_svg_and_rejects_executable_content(self):
        client = TestClient(app)
        with tempfile.TemporaryDirectory() as tmp:
            downloads = Path(tmp) / "Downloads"
            with patch("src.system_downloads.resolve_downloads_dir", return_value=downloads):
                accepted = client.post(
                    "/api/downloads/text",
                    json={"filename": "rnn-evaluation.svg", "content": "<svg></svg>"},
                )
                rejected = client.post(
                    "/api/downloads/text",
                    json={"filename": "unsafe.exe", "content": "not executable"},
                )

            self.assertEqual(accepted.status_code, 200)
            self.assertTrue(Path(accepted.json()["saved_path"]).is_file())
            self.assertEqual(rejected.status_code, 400)


if __name__ == "__main__":
    unittest.main()
