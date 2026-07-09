import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class I18nAuditScriptStaticTests(unittest.TestCase):
    def test_dom_audit_documents_runtime_and_attribute_scope(self):
        script = (ROOT / "scripts" / "i18n_dom_audit.mjs").read_text(encoding="utf-8")

        self.assertIn("PLAYWRIGHT_NODE_MODULES", script)
        self.assertIn("visibleText", script)
        self.assertIn("placeholder", script)
        self.assertIn("aria-label", script)
        self.assertIn("alt", script)
        self.assertIn("title", script)


if __name__ == "__main__":
    unittest.main()
