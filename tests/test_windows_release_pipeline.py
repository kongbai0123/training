from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WindowsReleasePipelineTests(unittest.TestCase):
    def test_installer_uses_supported_x64_identifier_and_strong_compression(self):
        config = (ROOT / "installer" / "VisionTrainingStudio.iss").read_text(encoding="utf-8")
        self.assertIn("ArchitecturesAllowed=x64compatible", config)
        self.assertIn("ArchitecturesInstallIn64BitMode=x64compatible", config)
        self.assertIn("Compression=lzma2/ultra64", config)
        self.assertNotIn("ArchitecturesAllowed=x64\n", config)

    def test_formal_release_verifies_installer_authenticode(self):
        publisher = (ROOT / "scripts" / "publish_update_release.ps1").read_text(encoding="utf-8")
        verifier = (ROOT / "scripts" / "verify_windows_release.ps1").read_text(encoding="utf-8")
        self.assertIn("verify_windows_release.ps1", publisher)
        self.assertIn('if ($signature.Status -ne "Valid")', verifier)
        self.assertIn("Authenticode signature is required for publication", verifier)
        self.assertIn("2147483648", verifier)

    def test_installer_build_propagates_signing_failures_and_reads_version(self):
        builder = (ROOT / "scripts" / "build_installer.bat").read_text(encoding="utf-8")
        self.assertIn("if errorlevel 1", builder.lower())
        self.assertIn("set /p APP_VERSION=<VERSION", builder)
        self.assertNotIn("SETUP_EXE=installer\\output\\VisionTrainingStudio_Setup_0.2.0.exe", builder)

    def test_full_installer_can_replace_incremental_release_asset(self):
        publisher = (ROOT / "scripts" / "publish_update_release.ps1").read_text(encoding="utf-8")
        self.assertIn("-not $hasUpdate -and -not $hasSetup", publisher)


if __name__ == "__main__":
    unittest.main()
