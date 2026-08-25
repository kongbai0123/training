import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UnifiedOverviewStaticTests(unittest.TestCase):
    def read(self, *parts):
        return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")

    def test_dashboard_is_a_data_driven_module_platform(self):
        dashboard = self.read("static", "pages", "dashboard.js")
        index_html = self.read("static", "index.html")

        self.assertIn("export const OVERVIEW_MODULES", dashboard)
        self.assertIn('mode: "rnn"', dashboard)
        self.assertIn('mode: "cnn"', dashboard)
        self.assertIn('mode: "tabular"', dashboard)
        self.assertIn('eventBus.emit("open-training-module"', dashboard)
        self.assertIn("overview-module-context no-i18n", dashboard)
        self.assertIn('id="overview-module-grid"', index_html)
        self.assertNotIn('class="training-mode-toggle"', index_html)
        self.assertNotIn("renderProjectStatusStrip", dashboard)

    def test_module_cards_are_compact_responsive_windows(self):
        dashboard_css = self.read("static", "styles", "pages", "dashboard.css")

        self.assertIn(".overview-module-grid {", dashboard_css)
        self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr));", dashboard_css)
        self.assertIn(".overview-module-tabular {", dashboard_css)
        self.assertIn(".overview-module-icon {", dashboard_css)
        self.assertIn("width: 38px;", dashboard_css)
        self.assertIn("@media (max-width: 1180px) {", dashboard_css)

    def test_module_catalog_keys_exist_in_both_languages(self):
        en = self.read("static", "state", "i18n", "en.js")
        zh = self.read("static", "state", "i18n", "zh-TW.js")
        for key in (
            "dashboard.modules.title",
            "dashboard.module.cnn.title",
            "dashboard.module.rnn.title",
            "dashboard.module.tabular.title",
            "dashboard.module.open",
            "dashboard.activity.noProject",
        ):
            self.assertIn(f'"{key}"', en)
            self.assertIn(f'"{key}"', zh)


if __name__ == "__main__":
    unittest.main()
