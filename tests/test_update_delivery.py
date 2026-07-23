from __future__ import annotations

import hashlib
import io
from pathlib import Path
import tempfile
import unittest

from src.update.downloader import download_release_asset
from src.update.github_client import GitHubReleaseClient, ReleaseAsset
from src.update.versioning import VersionInfo


class FakeResponse(io.BytesIO):
    def __init__(self, content: bytes, status: int = 200):
        super().__init__(content)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def current_version() -> VersionInfo:
    return VersionInfo.from_mapping(
        {
            "product": "Vision Training Studio",
            "app_version": "0.1.4",
            "runtime_version": "r1",
            "package_format_version": 1,
            "update_channel": "stable",
        }
    )


class UpdateDeliveryTests(unittest.TestCase):
    def test_release_client_selects_matching_runtime_asset(self):
        payload = {
            "tag_name": "v0.1.5",
            "draft": False,
            "prerelease": False,
            "immutable": True,
            "html_url": "https://github.com/kongbai0123/training/releases/tag/v0.1.5",
            "published_at": "2026-07-23T10:00:00Z",
            "body": "Notes",
            "assets": [
                {
                    "id": 1,
                    "name": "VisionTrainingStudio_Update_0.1.5_runtime-r2.vtsupdate",
                    "browser_download_url": "https://github.com/kongbai0123/training/releases/download/v0.1.5/r2.vtsupdate",
                    "size": 10,
                    "digest": "",
                },
                {
                    "id": 2,
                    "name": "VisionTrainingStudio_Update_0.1.5_runtime-r1.vtsupdate",
                    "browser_download_url": "https://github.com/kongbai0123/training/releases/download/v0.1.5/update.vtsupdate",
                    "size": 20,
                    "digest": "sha256:" + "a" * 64,
                },
                {
                    "id": 3,
                    "name": "VisionTrainingStudio_Setup_0.1.5.exe",
                    "browser_download_url": "https://github.com/kongbai0123/training/releases/download/v0.1.5/setup.exe",
                    "size": 100,
                    "digest": "",
                },
            ],
        }
        candidate = GitHubReleaseClient()._candidate_from_release(payload, current_version())
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.asset.asset_id, 2)
        self.assertEqual(candidate.runtime_version, "r1")
        self.assertEqual(candidate.full_installer.asset_id, 3)

    def test_release_client_ignores_old_release(self):
        old = {"tag_name": "v0.1.4", "draft": False, "prerelease": False, "assets": []}
        self.assertIsNone(GitHubReleaseClient()._candidate_from_release(old, current_version()))

    def test_download_verifies_size_digest_and_reports_progress(self):
        content = b"signed-update-content"
        asset = ReleaseAsset(
            asset_id=10,
            name="update.vtsupdate",
            url="https://github.com/kongbai0123/training/releases/download/v0.1.5/update.vtsupdate",
            size=len(content),
            digest="sha256:" + hashlib.sha256(content).hexdigest(),
        )
        progress = []
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "update.vtsupdate"
            result = download_release_asset(
                asset,
                target,
                opener=lambda *_args, **_kwargs: FakeResponse(content),
                progress=progress.append,
                minimum_free_bytes=0,
            )
            self.assertEqual(result.read_bytes(), content)
            self.assertEqual(progress[-1]["progress"], 100.0)

    def test_download_rejects_untrusted_host_and_bad_digest(self):
        content = b"content"
        bad_host = ReleaseAsset(1, "x", "https://example.com/x", len(content), "")
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "approved HTTPS"):
                download_release_asset(bad_host, Path(temp) / "x", minimum_free_bytes=0)
            bad_digest = ReleaseAsset(
                2,
                "x",
                "https://github.com/kongbai0123/training/releases/download/v1/x",
                len(content),
                "sha256:" + "0" * 64,
            )
            with self.assertRaisesRegex(ValueError, "checksum"):
                download_release_asset(
                    bad_digest,
                    Path(temp) / "x",
                    opener=lambda *_args, **_kwargs: FakeResponse(content),
                    minimum_free_bytes=0,
                )
