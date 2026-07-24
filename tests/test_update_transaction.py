from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.update.baseline import build_runtime_baseline
from src.update.package_builder import build_update_package
from src.update.transaction import UpdateJournal, apply_update, prepare_update, recover_incomplete_update


def write_version(path: Path, app: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "product": "Vision Training Studio",
                "version": app,
                "app_version": app,
                "runtime_version": "r1",
                "package_format_version": 1,
                "update_channel": "stable",
            }
        ),
        encoding="utf-8",
    )


def write_keys(private_path: Path, public_path: Path) -> None:
    key = Ed25519PrivateKey.generate()
    private_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )


class UpdateTransactionTests(unittest.TestCase):
    def _fixture(self, root: Path):
        base_dist = root / "base-dist"
        target_dist = root / "target-dist"
        for dist in (base_dist, target_dist):
            (dist / "_internal" / "static").mkdir(parents=True)
            (dist / "VisionTrainingStudio.exe").write_bytes(b"app-v1")
            (dist / "_internal" / "static" / "app.js").write_text("old-ui", encoding="utf-8")
            (dist / "_internal" / "runtime.dll").write_bytes(b"runtime-r1")
            write_version(dist / "_internal" / "version.json", "0.1.3")
        base_version = root / "base-version.json"
        target_version = root / "target-version.json"
        write_version(base_version, "0.1.3")
        write_version(target_version, "0.1.4")
        write_version(target_dist / "_internal" / "version.json", "0.1.4")
        (target_dist / "VisionTrainingStudio.exe").write_bytes(b"app-v2")
        (target_dist / "_internal" / "static" / "app.js").write_text("new-ui", encoding="utf-8")
        baseline = root / "baseline.json"
        build_runtime_baseline(base_dist, base_version, baseline)
        private_key = root / "private.pem"
        public_key = root / "public.pem"
        write_keys(private_key, public_key)
        package = root / "update.vtsupdate"
        build_update_package(target_dist, baseline, target_version, private_key, package)
        return base_dist, package, public_key

    def test_apply_signed_update_and_preserve_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            install, package, public_key = self._fixture(root)
            journal = prepare_update(
                package,
                install,
                install / "_internal" / "version.json",
                public_key,
                root / "updates",
            )
            self.assertEqual(journal.read()["state"], "staged")
            result = apply_update(journal)
            self.assertEqual(result["state"], "completed")
            self.assertEqual((install / "VisionTrainingStudio.exe").read_bytes(), b"app-v2")
            self.assertEqual((install / "_internal" / "static" / "app.js").read_text(), "new-ui")
            self.assertEqual((install / "_internal" / "runtime.dll").read_bytes(), b"runtime-r1")
            self.assertEqual(json.loads((install / "_internal" / "version.json").read_text())["version"], "0.1.4")

    def test_apply_failure_rolls_back_every_replaced_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            install, package, public_key = self._fixture(root)
            journal = prepare_update(
                package,
                install,
                install / "_internal" / "version.json",
                public_key,
                root / "updates",
            )
            payload = journal.read()
            staged_version = Path(payload["staging_dir"]) / "_internal" / "version.json"
            staged_version.write_text("{broken", encoding="utf-8")
            with self.assertRaises(ValueError):
                apply_update(journal)
            self.assertEqual(journal.read()["state"], "rolled_back")
            self.assertEqual((install / "VisionTrainingStudio.exe").read_bytes(), b"app-v1")
            self.assertEqual((install / "_internal" / "static" / "app.js").read_text(), "old-ui")
            self.assertEqual(json.loads((install / "_internal" / "version.json").read_text())["version"], "0.1.3")

    def test_recover_incomplete_application_restores_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            install = root / "install"
            install.mkdir()
            (install / "VisionTrainingStudio.exe").write_bytes(b"new")
            backup = root / "backup"
            backup.mkdir()
            (backup / "VisionTrainingStudio.exe").write_bytes(b"old")
            journal = UpdateJournal(root / "journal.json")
            journal.write(
                {
                    "schema_version": 1,
                    "state": "applying",
                    "install_dir": install.as_posix(),
                    "backup_dir": backup.as_posix(),
                    "backed_up": ["VisionTrainingStudio.exe"],
                    "missing_before": [],
                    "applied": ["VisionTrainingStudio.exe"],
                    "remove": [],
                    "history": [],
                }
            )
            result = recover_incomplete_update(journal)
            self.assertEqual(result["state"], "rolled_back")
            self.assertEqual((install / "VisionTrainingStudio.exe").read_bytes(), b"old")
