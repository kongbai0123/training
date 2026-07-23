from pathlib import Path
import unittest
import json


ROOT = Path(__file__).resolve().parents[1]


class ScriptsContractTests(unittest.TestCase):
    def test_release_version_is_synchronized(self):
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        installer = (ROOT / "installer" / "VisionTrainingStudio.iss").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        version_info = json.loads((ROOT / "version.json").read_text(encoding="utf-8"))
        self.assertIn(f'#define MyAppVersion "{version}"', installer)
        self.assertIn(f"version-{version}-2563EB", readme)
        self.assertEqual(version_info["version"], version)

    def test_required_windows_scripts_exist(self):
        for script in [
            "start.bat",
            "start_dev.bat",
            "test.bat",
            "build.bat",
            "package.bat",
            "package_portable.bat",
            "smoke_dist.bat",
            "smoke_dist_portable.bat",
            "smoke_dist_offline.ps1",
            "smoke_labelme_component.py",
            "audit_pyinstaller_warnings.bat",
        ]:
            with self.subTest(script=script):
                self.assertTrue((ROOT / "scripts" / script).exists())

    def test_test_dependencies_are_separate_from_runtime_requirements(self):
        runtime = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        test = (ROOT / "requirements-test.txt").read_text(encoding="utf-8")

        self.assertNotIn("pytest==", runtime)
        self.assertNotIn("httpx2==", runtime)
        self.assertIn("pytest==8.3.5", test)
        self.assertIn("httpx2==2.5.0", test)

    def test_start_script_uses_launcher_entrypoint(self):
        start_script = (ROOT / "scripts" / "start.bat").read_text(encoding="utf-8")

        self.assertIn("launcher.py", start_script)
        self.assertIn("--env production", start_script)
        self.assertIn("--port 18080", start_script)
        self.assertIn("%*", start_script)

    def test_frozen_launcher_initializes_windows_multiprocessing_workers(self):
        launcher = (ROOT / "launcher.py").read_text(encoding="utf-8")

        self.assertIn("multiprocessing.freeze_support()", launcher)
        self.assertLess(
            launcher.index("multiprocessing.freeze_support()"),
            launcher.index("    main()", launcher.index('if __name__ == "__main__":')),
        )

    def test_desktop_launcher_shows_staged_startup_feedback(self):
        launcher = (ROOT / "launcher.py").read_text(encoding="utf-8")
        splash = (ROOT / "src" / "startup_splash.py").read_text(encoding="utf-8")

        self.assertIn("StartupSplash(enabled=should_show_startup_splash(shell))", launcher)
        self.assertIn("on_wait=report_backend_wait", launcher)
        self.assertIn("splash.show_error(", launcher)
        self.assertIn("multiprocessing.freeze_support()", launcher)
        for phase in (
            "啟動應用程式",
            "準備本機 AI 服務",
            "檢查硬體與專案資料",
            "開啟工作區",
        ):
            self.assertIn(phase, splash)
        self.assertIn('shell or "").strip().lower() == "none"', splash)
        self.assertIn("VTS_DISABLE_SPLASH", splash)
        self.assertIn("已等待 {seconds} 秒", splash)

    def test_pyinstaller_spec_filters_optional_warning_noise_during_collection(self):
        spec = (ROOT / "packaging" / "vision_training_studio.spec").read_text(encoding="utf-8")

        self.assertIn("filter_submodules=keep_hidden_import", spec)
        for optional_runtime in ("tensorflow", "diffusers", "transformers", "gradio", "yt_dlp"):
            self.assertIn(f'"{optional_runtime}"', spec)
        self.assertIn("collect_submodules(package_name, filter=keep_hidden_import)", spec)
        self.assertIn('copy_metadata("opencv-python")', spec)
        self.assertIn('"xgboost.dask"', spec)
        self.assertIn('"onnx.reference"', spec)
        self.assertIn('"bottle"', spec)
        self.assertNotIn('"bottle",\n    "xgboost"', spec)

    def test_package_script_stops_locked_dist_process_before_rebuild(self):
        package_script = (ROOT / "scripts" / "package.bat").read_text(encoding="utf-8")

        self.assertIn("dist\\VisionTrainingStudio", package_script)
        self.assertIn("Unable to stop packaged app process", package_script)
        self.assertIn("VTS_PYTHON_EXE", package_script)

    def test_installer_build_supports_per_user_inno_setup(self):
        installer_script = (ROOT / "scripts" / "build_installer.bat").read_text(encoding="utf-8")

        self.assertIn("%LOCALAPPDATA%\\Programs\\Inno Setup 6\\ISCC.exe", installer_script)

    def test_pyinstaller_warning_audit_script_has_blocker_gate(self):
        audit_script = (ROOT / "scripts" / "audit_pyinstaller_warnings.py").read_text(encoding="utf-8")

        self.assertIn("BLOCKER_PATTERNS", audit_script)
        self.assertIn("unclassified", audit_script)
        self.assertIn("watchfiles", audit_script)
        self.assertIn("OpenSSL", audit_script)
        self.assertIn("scipy\\.optimize", audit_script)
        self.assertIn("numba\\.", audit_script)
        self.assertIn("return 1", audit_script)

    def test_dist_smoke_uses_clean_user_data_and_checks_runtime(self):
        smoke_script = (ROOT / "scripts" / "smoke_dist_offline.ps1").read_text(encoding="utf-8")

        self.assertIn("dist-smoke-", smoke_script)
        self.assertIn('$env:LOCALAPPDATA = $smokeRoot', smoke_script)
        self.assertIn("/api/system/capabilities", smoke_script)
        self.assertIn("/api/projects", smoke_script)
        self.assertIn("Factory-clean package exposed", smoke_script)
        self.assertIn("Get-CimInstance Win32_Process", smoke_script)
        self.assertIn('HTTP_PROXY = "http://127.0.0.1:9"', smoke_script)
        self.assertIn("externalConnections", smoke_script)
        self.assertIn('New-Item -ItemType File -Path $portableMarker', smoke_script)
        self.assertIn('[string]$ExePath', smoke_script)
        self.assertIn('$portableMarkerPreexisting', smoke_script)

    def test_portable_packager_enforces_factory_clean_contract(self):
        packager = (ROOT / "scripts" / "package_portable.py").read_text(encoding="utf-8")

        self.assertIn("FORBIDDEN_ROOTS", packager)
        self.assertIn('archive.writestr(f"{archive_root}/portable.mode"', packager)
        self.assertIn("allowZip64=True", packager)
        self.assertIn("archive.testzip()", packager)


if __name__ == "__main__":
    unittest.main()
