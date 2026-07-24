from __future__ import annotations

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.update.baseline import build_runtime_baseline
from src.update.github_client import ReleaseAsset, UpdateCandidate
from src.update.package_builder import build_update_package
from src.update.service import UpdateService
from src.update.storage import UPDATE_CACHE_LIMIT_BYTES, cleanup_update_storage, update_storage_report
from src.update.versioning import ProductVersion, VersionInfo


def write_version(path: Path, version: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "product": "Vision Training Studio",
                "version": version,
                "app_version": version,
                "runtime_version": "r1",
                "package_format_version": 1,
                "update_channel": "stable",
            }
        ),
        encoding="utf-8",
    )


class FakeReleaseClient:
    def latest_stable(self, _current):
        return UpdateCandidate(
            version=ProductVersion.parse("0.1.4"),
            runtime_version="r1",
            tag="v0.1.4",
            release_url="https://github.com/kongbai0123/training/releases/tag/v0.1.4",
            published_at="2026-07-23T00:00:00Z",
            notes="Update",
            immutable=True,
            asset=ReleaseAsset(
                1,
                "VisionTrainingStudio_Update_0.1.4_runtime-r1.vtsupdate",
                "https://github.com/kongbai0123/training/releases/download/v0.1.4/update.vtsupdate",
                100,
                "",
            ),
            full_installer=None,
        )


class FullInstallerReleaseClient:
    def latest_stable(self, _current):
        return UpdateCandidate(
            version=ProductVersion.parse("0.1.4"),
            runtime_version="r1",
            tag="v0.1.4",
            release_url="https://github.com/kongbai0123/training/releases/tag/v0.1.4",
            published_at="2026-07-23T00:00:00Z",
            notes="Full installer required",
            immutable=True,
            asset=None,
            full_installer=ReleaseAsset(
                2,
                "VisionTrainingStudio_Setup_0.1.4.exe",
                "https://github.com/kongbai0123/training/releases/download/v0.1.4/setup.exe",
                1024,
                "",
            ),
        )


class UpdateServiceTests(unittest.TestCase):
    def setUp(self):
        self.current = VersionInfo.from_mapping(
            {
                "product": "Vision Training Studio",
                "app_version": "0.1.3",
                "runtime_version": "r1",
                "package_format_version": 1,
                "update_channel": "stable",
            }
        )

    def test_check_persists_candidate_and_survives_service_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            kwargs = {
                "downloads_dir": root / "downloads",
                "state_file": root / "state.json",
                "public_key_path": root / "public.pem",
                "release_client": FakeReleaseClient(),
                "current_version": self.current,
            }
            service = UpdateService(**kwargs)
            result = service.check_for_updates()
            self.assertEqual(result["candidate"]["version"], "0.1.4")
            restored = UpdateService(**kwargs)
            self.assertEqual(restored.status()["candidate"]["asset"]["asset_id"], 1)

    def test_offline_import_registers_only_verified_compatible_package(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base_dist = root / "base"
            target_dist = root / "target"
            for dist in (base_dist, target_dist):
                (dist / "_internal" / "static").mkdir(parents=True)
                (dist / "VisionTrainingStudio.exe").write_bytes(b"old")
                (dist / "_internal" / "runtime.dll").write_bytes(b"runtime")
                (dist / "_internal" / "static" / "app.js").write_bytes(b"old")
                write_version(dist / "_internal" / "version.json", "0.1.3")
            base_version = root / "base.json"
            target_version = root / "target.json"
            write_version(base_version, "0.1.3")
            write_version(target_version, "0.1.4")
            write_version(target_dist / "_internal" / "version.json", "0.1.4")
            (target_dist / "VisionTrainingStudio.exe").write_bytes(b"new")
            baseline = root / "baseline.json"
            build_runtime_baseline(base_dist, base_version, baseline)
            key = Ed25519PrivateKey.generate()
            private = root / "private.pem"
            public = root / "public.pem"
            private.write_bytes(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
            public.write_bytes(
                key.public_key().public_bytes(
                    serialization.Encoding.PEM,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            )
            package = root / "update.vtsupdate"
            build_update_package(target_dist, baseline, target_version, private, package)
            service = UpdateService(
                downloads_dir=root / "downloads",
                state_file=root / "state.json",
                public_key_path=public,
                release_client=FakeReleaseClient(),
                current_version=self.current,
            )
            result = service.register_imported_package(package)
            self.assertEqual(result["app_version"], "0.1.4")
            self.assertEqual(service.status()["ready_package"]["source"], "offline_import")

    def test_status_discards_same_version_ready_package_and_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            downloads = root / "updates" / "downloads"
            downloads.mkdir(parents=True)
            package = downloads / "same.vtsupdate"
            package.write_bytes(b"obsolete")
            state = root / "state.json"
            state.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "last_checked_at": "",
                        "candidate": {"version": "0.1.3"},
                        "ready_package": {
                            "path": package.as_posix(),
                            "app_version": "0.1.3",
                            "runtime_version": "r1",
                        },
                        "last_error": "",
                    }
                ),
                encoding="utf-8",
            )
            service = UpdateService(
                downloads_dir=downloads,
                state_file=state,
                public_key_path=root / "public.pem",
                current_version=self.current,
            )
            result = service.status()
            self.assertIsNone(result["ready_package"])
            self.assertIsNone(result["candidate"])
            self.assertFalse(package.exists())
            self.assertFalse(result["can_apply"])

    def test_cleanup_retains_ready_download_and_only_latest_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "updates"
            downloads = root / "downloads"
            staging = root / "staging"
            backups = root / "backups"
            journals = root / "journals"
            for path in (downloads, staging, backups, journals):
                path.mkdir(parents=True)
            ready = downloads / "ready.vtsupdate"
            ready.write_bytes(b"ready")
            (downloads / "old.part").write_bytes(b"partial")
            (staging / "old").mkdir()
            (staging / "old" / "payload").write_bytes(b"staged")
            for index in range(2):
                backup = backups / f"backup-{index}"
                backup.mkdir()
                (backup / "file").write_bytes(bytes([index]))
                backup.touch()
            for index in range(12):
                journal = journals / f"journal-{index:02}.json"
                journal.write_text("{}", encoding="utf-8")
                journal.touch()

            report = cleanup_update_storage(root, preserve_downloads=[ready])
            self.assertTrue(ready.exists())
            self.assertFalse((downloads / "old.part").exists())
            self.assertEqual(len(list(backups.iterdir())), 1)
            self.assertEqual(len(list(journals.glob("*.json"))), 10)
            self.assertGreater(report["freed_bytes"], 0)

    def test_import_budget_enforces_two_gib_update_cache_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            downloads = root / "updates" / "downloads"
            downloads.mkdir(parents=True)
            existing = downloads / "existing.bin"
            with existing.open("wb") as stream:
                stream.truncate(1024)
            service = UpdateService(
                downloads_dir=downloads,
                state_file=root / "state.json",
                public_key_path=root / "public.pem",
                current_version=self.current,
            )
            self.assertEqual(
                service.import_budget("new.vtsupdate"),
                UPDATE_CACHE_LIMIT_BYTES - 1024,
            )
            report = update_storage_report(root / "updates")
            self.assertEqual(report["cache_limit_bytes"], UPDATE_CACHE_LIMIT_BYTES)

    def test_one_click_github_download_checks_downloads_verifies_and_prevents_repeat(self):
        class Reporter:
            def update(self, **_values):
                return None

            def is_cancelled(self):
                return False

        def submit_now(*, handler, **_values):
            return handler(Reporter())

        def download_now(asset, destination, *, progress):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"x")
            progress(
                {
                    "progress": 100,
                    "downloaded_bytes": asset.size,
                    "total_bytes": asset.size,
                }
            )
            return destination

        verified = SimpleNamespace(
            manifest={
                "product": "Vision Training Studio",
                "target_app_version": "0.1.4",
                "runtime_version": "r1",
                "format_version": 1,
                "supported_from": ["0.1.3"],
            },
            archive_sha256="a" * 64,
            archive_bytes=1,
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service = UpdateService(
                downloads_dir=root / "updates" / "downloads",
                state_file=root / "state.json",
                public_key_path=root / "public.pem",
                release_client=FakeReleaseClient(),
                current_version=self.current,
            )
            with (
                patch("src.update.service.task_job_manager.submit", side_effect=submit_now),
                patch("src.update.service.download_release_asset", side_effect=download_now) as download,
                patch("src.update.service.verify_update_archive", return_value=verified),
            ):
                result = service.start_latest_download()
                self.assertEqual(result["source"], "github_release")
                self.assertEqual(service.status()["ready_package"]["app_version"], "0.1.4")
                with self.assertRaisesRegex(ValueError, "already downloaded"):
                    service.start_latest_download()
                self.assertEqual(download.call_count, 1)

    def test_one_click_check_returns_full_installer_guidance_without_downloading(self):
        class Reporter:
            def update(self, **_values):
                return None

        def submit_now(*, handler, **_values):
            return handler(Reporter())

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service = UpdateService(
                downloads_dir=root / "updates" / "downloads",
                state_file=root / "state.json",
                public_key_path=root / "public.pem",
                release_client=FullInstallerReleaseClient(),
                current_version=self.current,
            )
            with (
                patch("src.update.service.task_job_manager.submit", side_effect=submit_now),
                patch("src.update.service.download_release_asset") as download,
            ):
                result = service.start_latest_download()
                self.assertEqual(result["candidate"]["delivery"], "full_installer")
                self.assertFalse(result["candidate"]["can_incremental_update"])
                self.assertIsNone(result["candidate"]["asset"])
                self.assertEqual(
                    result["candidate"]["full_installer"]["name"],
                    "VisionTrainingStudio_Setup_0.1.4.exe",
                )
                download.assert_not_called()
