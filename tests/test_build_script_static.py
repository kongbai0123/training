import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BuildScriptStaticTests(unittest.TestCase):
    def test_build_script_checks_modular_frontend_javascript(self):
        build_bat = (ROOT / "scripts" / "build.bat").read_text(encoding="utf-8")

        self.assertIn("for %%F in (", build_bat)
        self.assertIn("static\\*.js", build_bat)
        self.assertIn("static\\core\\*.js", build_bat)
        self.assertIn("static\\pages\\*.js", build_bat)
        self.assertIn("static\\state\\*.js", build_bat)
        self.assertIn("static\\state\\i18n\\*.js", build_bat)
        self.assertIn("static\\ui\\*.js", build_bat)
        self.assertIn('node --check "%%F" || exit /b 1', build_bat)
        self.assertNotIn("node --check static\\app.js || exit /b 1", build_bat)


if __name__ == "__main__":
    unittest.main()
