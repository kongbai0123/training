from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.update.baseline import build_runtime_baseline
from src.update.manifest import verify_update_archive
from src.update.package_builder import build_update_package
from src.update.paths import is_app_mutable_path, normalize_package_path
from src.update.versioning import (
    ProductVersion,
    VersionInfo,
    ensure_update_compatible,
    load_version_info,
)


def write_version(path: Path, app: str, runtime: str = "r1") -> None:
    path.write_text(
        json.dumps(
            {
                "product": "Vision Training Studio",
                "version": app,
                "app_version": app,
                "runtime_version": runtime,
                "package_format_version": 1,
                "update_channel": "stable",
            }
        ),
        encoding="utf-8",
    )


def create_key_pair(private_path: Path, public_path: Path) -> None:
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


class UpdateFoundationTests(unittest.TestCase):
    def test_product_version_is_strict_and_ordered(self):
        self.assertLess(ProductVersion.parse("0.1.3"), ProductVersion.parse("0.1.4"))
        self.assertEqual(str(ProductVersion.parse("12.3.45")), "12.3.45")
        for invalid in ("v0.1.3", "0.1", "01.2.3", "0.1.3-beta"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    ProductVersion.parse(invalid)

    def test_compatibility_requires_newer_app_and_same_runtime(self):
        current = VersionInfo.from_mapping(
            {
                "product": "Vision Training Studio",
                "app_version": "0.1.3",
                "runtime_version": "r1",
                "package_format_version": 1,
                "update_channel": "stable",
            }
        )
        target = VersionInfo.from_mapping(
            {
                "product": "Vision Training Studio",
                "app_version": "0.1.4",
                "runtime_version": "r1",
                "package_format_version": 1,
                "update_channel": "stable",
            }
        )
        ensure_update_compatible(current, target, ["0.1.3"])
        incompatible = VersionInfo(
            product=target.product,
            app_version=target.app_version,
            runtime_version="r2",
            package_format_version=1,
            update_channel="stable",
        )
        with self.assertRaisesRegex(ValueError, "full setup"):
            ensure_update_compatible(current, incompatible, ["0.1.3"])

    def test_package_paths_reject_user_data_and_traversal(self):
        self.assertTrue(is_app_mutable_path("VisionTrainingStudio.exe"))
        self.assertTrue(is_app_mutable_path("_internal/static/app.js"))
        for unsafe in (
            "../evil.exe",
            "C:/evil.exe",
            "/evil.exe",
            "_internal\\static\\evil.js",
            "projects/data.json",
            "models/model.pt",
        ):
            with self.subTest(unsafe=unsafe):
                with self.assertRaises(ValueError):
                    normalize_package_path(unsafe)

    def test_signed_package_round_trip_and_runtime_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dist = root / "dist"
            (dist / "_internal" / "static").mkdir(parents=True)
            (dist / "_internal").mkdir(exist_ok=True)
            (dist / "VisionTrainingStudio.exe").write_bytes(b"app-v1")
            (dist / "_internal" / "static" / "app.js").write_text("v1", encoding="utf-8")
            (dist / "_internal" / "runtime.dll").write_bytes(b"runtime-r1")
            base_version = root / "base-version.json"
            target_version = root / "target-version.json"
            write_version(base_version, "0.1.3")
            write_version(target_version, "0.1.4")
            write_version(dist / "_internal" / "version.json", "0.1.3")
            baseline = root / "runtime-r1.json"
            build_runtime_baseline(dist, base_version, baseline)

            (dist / "VisionTrainingStudio.exe").write_bytes(b"app-v2")
            (dist / "_internal" / "static" / "app.js").write_text("v2", encoding="utf-8")
            write_version(dist / "_internal" / "version.json", "0.1.4")
            private_key = root / "private.pem"
            public_key = root / "public.pem"
            create_key_pair(private_key, public_key)
            package = root / "update.vtsupdate"
            result = build_update_package(
                dist,
                baseline,
                target_version,
                private_key,
                package,
                release_notes_zh="更新",
            )
            self.assertEqual(result["changed_file_count"], 3)
            verified = verify_update_archive(package, public_key)
            self.assertEqual(verified.manifest["target_app_version"], "0.1.4")
            self.assertEqual(verified.manifest["runtime_version"], "r1")

            (dist / "_internal" / "runtime.dll").write_bytes(b"changed-runtime")
            with self.assertRaisesRegex(ValueError, "full installer"):
                build_update_package(
                    dist,
                    baseline,
                    target_version,
                    private_key,
                    root / "unsafe.vtsupdate",
                )

    def test_tampered_payload_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dist = root / "dist"
            (dist / "_internal" / "static").mkdir(parents=True)
            (dist / "VisionTrainingStudio.exe").write_bytes(b"v1")
            (dist / "_internal" / "static" / "app.js").write_text("v1", encoding="utf-8")
            base_version = root / "base.json"
            target_version = root / "target.json"
            write_version(base_version, "0.1.3")
            write_version(target_version, "0.1.4")
            write_version(dist / "_internal" / "version.json", "0.1.3")
            baseline = root / "baseline.json"
            build_runtime_baseline(dist, base_version, baseline)
            (dist / "VisionTrainingStudio.exe").write_bytes(b"v2")
            write_version(dist / "_internal" / "version.json", "0.1.4")
            private_key = root / "private.pem"
            public_key = root / "public.pem"
            create_key_pair(private_key, public_key)
            package = root / "valid.vtsupdate"
            build_update_package(dist, baseline, target_version, private_key, package)

            tampered = root / "tampered.vtsupdate"
            with zipfile.ZipFile(package, "r") as source, zipfile.ZipFile(tampered, "w") as target:
                for info in source.infolist():
                    content = source.read(info.filename)
                    if info.filename == "payload/VisionTrainingStudio.exe":
                        content = b"tampered"
                    target.writestr(info, content)
            with self.assertRaisesRegex(ValueError, "size mismatch|digest mismatch"):
                verify_update_archive(tampered, public_key)

    def test_repository_version_has_dual_version_fields(self):
        root = Path(__file__).resolve().parents[1]
        info = load_version_info(root / "version.json")
        self.assertEqual(str(info.app_version), "0.1.3")
        self.assertEqual(info.runtime_version, "r1")
