from __future__ import annotations

import json
import hashlib
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PersonalBootstrapLauncherTests(unittest.TestCase):
    def setUp(self):
        self.launcher = (ROOT / "啟動 Vision Training Studio.bat").read_text(encoding="utf-8")
        self.script = (ROOT / "scripts" / "bootstrap_personal.ps1").read_text(encoding="utf-8")
        self.manifest = json.loads((ROOT / "bootstrap-manifest.json").read_text(encoding="utf-8"))

    def test_root_launcher_uses_only_windows_builtins(self):
        self.assertIn("powershell.exe", self.launcher)
        self.assertIn("-ExecutionPolicy Bypass", self.launcher)
        self.assertIn("scripts\\bootstrap_personal.ps1", self.launcher)
        self.assertNotIn("python", self.launcher.lower())
        self.assertNotIn("node", self.launcher.lower())
        self.assertIn(
            '$ManifestPath = Join-Path (Split-Path -Parent $PSScriptRoot) "bootstrap-manifest.json"',
            self.script,
        )

    def test_manifest_pins_one_exact_installer(self):
        installer = self.manifest["installer"]
        self.assertEqual(self.manifest["schema_version"], 1)
        self.assertEqual(self.manifest["product"], "Vision Training Studio")
        self.assertEqual(self.manifest["version"], "0.2.0")
        self.assertTrue(self.manifest["package_id"])
        self.assertEqual(installer["file_name"], "VisionTrainingStudio_Setup_0.2.0.exe")
        self.assertTrue(installer["url"].startswith("https://github.com/kongbai0123/training/releases/download/"))
        self.assertGreater(installer["bytes"], 0)
        self.assertRegex(installer["sha256"], r"^[a-f0-9]{64}$")

    def test_bootstrap_verifies_and_never_installs_a_partial_download(self):
        for contract in (
            '"$installerPath.part"',
            "for ($attempt = 1; $attempt -le 3; $attempt++)",
            "Test-InstallerPayload",
            "Get-Sha256",
            "ExpectedBytes",
            "ExpectedSha256",
            "Move-Item -LiteralPath $partialPath -Destination $installerPath -Force",
            'response.Headers["Content-Range"]',
            "The download exceeded the expected installer size",
            'installerUri.Host -ne "github.com"',
            "GetFileName($installerFileName)",
        ):
            self.assertIn(contract, self.script)
        self.assertLess(
            self.script.index("Test-InstallerPayload -Path $partialPath"),
            self.script.index("Start-Process -FilePath $installerPath"),
        )

    def test_installer_is_per_user_silent_and_creates_desktop_shortcut(self):
        self.assertIn('"/SILENT"', self.script)
        self.assertIn('"/TASKS=desktopicon"', self.script)
        self.assertIn("'/DIR=\"{0}\"'", self.script)
        self.assertIn("bootstrap-state.json", self.script)
        self.assertIn("Get-InstalledExecutable", self.script)
        self.assertIn("Test-InstalledPackage", self.script)
        self.assertIn('"_internal\\version.json"', self.script)
        self.assertIn("Starting the installed application", self.script)
        self.assertIn("VisionTrainingStudioPersonalBootstrap", self.script)
        self.assertIn('$ProgressPreference = "Continue"', self.script)
        self.assertNotIn('"/CLOSEAPPLICATIONS"', self.script)

    def test_bootstrap_does_not_add_remote_access_features(self):
        lowered = self.script.lower()
        for forbidden in (
            "0.0.0.0",
            "new-netfirewallrule",
            "netsh",
            "api token",
            "login",
            "allowremote",
        ):
            self.assertNotIn(forbidden, lowered)

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell bootstrap test")
    def test_download_only_recovers_from_a_partial_file_and_verifies_hash(self):
        payload = b"MZ" + (b"vision-training-studio-bootstrap" * 128)
        sha256 = hashlib.sha256(payload).hexdigest()

        class QuietHandler(SimpleHTTPRequestHandler):
            saw_range_request = False

            def log_message(self, _format, *_args):
                return

            def do_GET(self):
                range_header = self.headers.get("Range")
                if not range_header:
                    return super().do_GET()
                type(self).saw_range_request = True
                start = int(range_header.removeprefix("bytes=").split("-", 1)[0])
                body = payload[start:]
                self.send_response(206)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", f"bytes {start}-{len(payload) - 1}/{len(payload)}")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        with tempfile.TemporaryDirectory(prefix="vts-bootstrap-test-") as temp:
            temp_path = Path(temp)
            served = temp_path / "served"
            bootstrap_root = temp_path / "bootstrap"
            downloads = bootstrap_root / "downloads"
            served.mkdir()
            downloads.mkdir(parents=True)
            installer_name = "VisionTrainingStudio_Setup_test.exe"
            (served / installer_name).write_bytes(payload)
            (downloads / f"{installer_name}.part").write_bytes(payload[:37])

            handler = partial(QuietHandler, directory=str(served))
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                manifest_path = temp_path / "manifest.json"
                manifest_path.write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "product": "Vision Training Studio",
                            "version": "test",
                            "package_id": "test-package",
                            "installer": {
                                "file_name": installer_name,
                                "url": f"http://127.0.0.1:{server.server_port}/{installer_name}",
                                "bytes": len(payload),
                                "sha256": sha256,
                            },
                            "install": {
                                "registry_app_id": "vts-test",
                                "default_relative_dir": "Programs\\VisionTrainingStudio",
                                "relative_executable": "VisionTrainingStudio.exe",
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                result = subprocess.run(
                    [
                        "powershell.exe",
                        "-NoLogo",
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-File",
                        str(ROOT / "scripts" / "bootstrap_personal.ps1"),
                        "-ManifestPath",
                        str(manifest_path),
                        "-BootstrapRoot",
                        str(bootstrap_root),
                        "-DownloadOnly",
                        "-AllowInsecureDownload",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            completed = downloads / installer_name
            self.assertEqual(completed.read_bytes(), payload)
            self.assertFalse((downloads / f"{installer_name}.part").exists())
            self.assertIn("BOOTSTRAP_INSTALLER=", result.stdout)
            self.assertTrue(QuietHandler.saw_range_request)

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell bootstrap test")
    def test_default_manifest_path_launches_matching_installed_package_without_network(self):
        with tempfile.TemporaryDirectory(prefix="vts-bootstrap-installed-") as temp:
            temp_path = Path(temp)
            bootstrap_root = temp_path / "bootstrap"
            install_root = temp_path / "install"
            internal = install_root / "_internal"
            bootstrap_root.mkdir()
            internal.mkdir(parents=True)
            executable = install_root / "VisionTrainingStudio.exe"
            executable.write_bytes(b"MZ-test")
            (internal / "version.json").write_text(
                json.dumps({"version": self.manifest["version"]}),
                encoding="utf-8",
            )
            (bootstrap_root / "bootstrap-state.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "package_id": self.manifest["package_id"],
                        "installer_sha256": self.manifest["installer"]["sha256"],
                        "executable_path": str(executable),
                    }
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoLogo",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(ROOT / "scripts" / "bootstrap_personal.ps1"),
                    "-BootstrapRoot",
                    str(bootstrap_root),
                    "-InstallRoot",
                    str(install_root),
                    "-NoLaunch",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Starting the installed application", result.stdout)


if __name__ == "__main__":
    unittest.main()
