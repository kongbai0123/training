from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class UpdateReleaseContractTests(unittest.TestCase):
    def test_update_api_is_registered_and_exposes_required_actions(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        route_source = (ROOT / "src" / "api" / "routes" / "updates.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("app.include_router(updates_router)", app_source)
        for route in (
            '"/api/updates/status"',
            '"/api/updates/check"',
            '"/api/updates/download"',
            '"/api/updates/import"',
            '"/api/updates/apply"',
        ):
            self.assertIn(route, route_source)
        self.assertIn('endswith(".vtsupdate")', route_source)

    def test_settings_contains_update_controls_and_bilingual_copy(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "static" / "pages" / "settings.js").read_text(
            encoding="utf-8"
        )
        english = (ROOT / "static" / "state" / "i18n" / "en.js").read_text(
            encoding="utf-8"
        )
        chinese = (ROOT / "static" / "state" / "i18n" / "zh-TW.js").read_text(
            encoding="utf-8"
        )

        for element_id in (
            "btn-check-updates",
            "btn-download-update",
            "btn-import-update",
            "btn-apply-update",
            "input-update-package",
            "update-blockers",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("followServerTask(task.job_id", script)
        self.assertIn('"/api/updates/import"', script)
        self.assertIn('"/api/updates/apply"', script)
        for key in ("updates.title", "updates.check", "updates.restartApply"):
            self.assertIn(f'"{key}"', english)
            self.assertIn(f'"{key}"', chinese)

    def test_release_workflows_validate_updates_and_version_tags(self):
        update_workflow = (
            ROOT / ".github" / "workflows" / "update-validation.yml"
        ).read_text(encoding="utf-8")
        release_workflow = (
            ROOT / ".github" / "workflows" / "release-validation.yml"
        ).read_text(encoding="utf-8")
        release_script = (
            ROOT / "scripts" / "publish_update_release.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn('"test_update_*.py"', update_workflow)
        self.assertIn("windows-latest", update_workflow)
        self.assertIn("tags:", release_workflow)
        self.assertIn('"v*.*.*"', release_workflow)
        self.assertIn("Working tree must be clean", release_script)
        self.assertIn(".vtsupdate", release_script)
        self.assertIn("--draft", release_script)


if __name__ == "__main__":
    unittest.main()
