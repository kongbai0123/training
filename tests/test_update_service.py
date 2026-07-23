from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.update.baseline import build_runtime_baseline
from src.update.github_client import ReleaseAsset, UpdateCandidate
from src.update.package_builder import build_update_package
from src.update.service import UpdateService
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
