import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class I18nAuditScriptStaticTests(unittest.TestCase):
    def test_dom_audit_documents_runtime_and_attribute_scope(self):
        script = (ROOT / "scripts" / "i18n_dom_audit.mjs").read_text(encoding="utf-8")

        self.assertIn("PLAYWRIGHT_NODE_MODULES", script)
        self.assertIn("tools\", \"i18n-audit\", \"node_modules", script)
        self.assertIn("visibleText", script)
        self.assertIn("placeholder", script)
        self.assertIn("aria-label", script)
        self.assertIn("alt", script)
        self.assertIn("title", script)
        self.assertIn("parseAuditTargets", script)
        self.assertIn("navigateAuditTarget", script)
        self.assertIn("args.pages || args.nav", script)
        self.assertIn("pageAliases", script)
        self.assertIn('dashboard: "overview"', script)
        self.assertIn("data-nav", script)
        self.assertIn("data-rnn-nav", script)
        self.assertIn("data-cnn-nav", script)

    def test_dom_audit_runtime_manifest_is_isolated(self):
        manifest = (ROOT / "tools" / "i18n-audit" / "package.json").read_text(encoding="utf-8")

        self.assertIn('"private": true', manifest)
        self.assertIn('"playwright"', manifest)


if __name__ == "__main__":
    unittest.main()
