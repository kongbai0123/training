import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BuildScriptStaticTests(unittest.TestCase):
    def test_root_contains_only_the_personal_one_click_launcher(self):
        root_batch_files = [path.name for path in ROOT.glob("*.bat")]
        launcher = (ROOT / "啟動 Vision Training Studio.bat").read_text(encoding="utf-8")
        run_bat = (ROOT / "scripts" / "run.bat").read_text(encoding="utf-8")

        self.assertEqual(root_batch_files, ["啟動 Vision Training Studio.bat"])
        self.assertIn("scripts\\bootstrap_personal.ps1", launcher)
        self.assertIn("powershell.exe", launcher)
        self.assertNotIn("python", launcher.lower())
        self.assertNotIn("node", launcher.lower())
        self.assertIn('cd /d "%~dp0\\.."', run_bat)
        self.assertIn('start "Vision Training Studio API"', run_bat)

    def test_build_script_checks_modular_frontend_javascript(self):
        build_bat = (ROOT / "scripts" / "build.bat").read_text(encoding="utf-8")

        self.assertIn("for %%F in (", build_bat)
        self.assertIn("static\\*.js", build_bat)
        self.assertIn("static\\core\\*.js", build_bat)
        self.assertIn("static\\pages\\*.js", build_bat)
        self.assertIn("static\\state\\*.js", build_bat)
        self.assertIn("static\\state\\i18n\\*.js", build_bat)
        self.assertIn("static\\ui\\*.js", build_bat)
        self.assertIn("scripts\\i18n_dom_audit.mjs", build_bat)
        self.assertIn('node --check "%%F" || exit /b 1', build_bat)
        self.assertNotIn("node --check static\\app.js || exit /b 1", build_bat)


if __name__ == "__main__":
    unittest.main()
