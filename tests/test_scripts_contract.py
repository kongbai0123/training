from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ScriptsContractTests(unittest.TestCase):
    def test_required_windows_scripts_exist(self):
        for script in [
            "start.bat",
            "start_dev.bat",
            "test.bat",
            "build.bat",
            "package.bat",
            "smoke_dist.bat",
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

    def test_pyinstaller_spec_filters_optional_warning_noise_during_collection(self):
        spec = (ROOT / "packaging" / "vision_training_studio.spec").read_text(encoding="utf-8")

        self.assertIn("filter_submodules=keep_hidden_import", spec)
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

    def test_pyinstaller_warning_audit_script_has_blocker_gate(self):
        audit_script = (ROOT / "scripts" / "audit_pyinstaller_warnings.py").read_text(encoding="utf-8")

        self.assertIn("BLOCKER_PATTERNS", audit_script)
        self.assertIn("unclassified", audit_script)
        self.assertIn("watchfiles", audit_script)
        self.assertIn("OpenSSL", audit_script)
        self.assertIn("return 1", audit_script)

    def test_dist_smoke_uses_clean_user_data_and_checks_runtime(self):
        smoke_script = (ROOT / "scripts" / "smoke_dist.bat").read_text(encoding="utf-8")

        self.assertIn("dist-smoke-local-app-data", smoke_script)
        self.assertIn("$env:LOCALAPPDATA=$smokeRoot", smoke_script)
        self.assertIn("/api/system/capabilities", smoke_script)
        self.assertIn("/api/projects", smoke_script)
        self.assertIn("Factory-clean package exposed", smoke_script)
        self.assertIn("Get-CimInstance Win32_Process", smoke_script)


if __name__ == "__main__":
    unittest.main()
