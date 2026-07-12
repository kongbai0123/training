import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ModelGuidePageStaticTests(unittest.TestCase):
    def test_model_guide_is_a_shared_navigation_page(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-page="model-guide"', html)
        self.assertIn('id="page-model-guide"', html)
        self.assertIn('id="model-guide-list"', html)
        self.assertIn('id="model-guide-detail"', html)
        self.assertIn('id="model-guide-decision"', html)
        self.assertIn('id="model-guide-report-preview"', html)
        self.assertLess(html.index('data-page="settings"'), html.index('data-page="model-guide"'))
        self.assertLess(html.index('data-page="model-guide"'), html.index('class="training-sidebar-divider"'))

    def test_model_guide_reuses_catalog_and_local_run_contracts(self):
        module = (ROOT / "static" / "pages" / "model_guide.js").read_text(encoding="utf-8")
        registry = (ROOT / "static" / "core" / "page_registry.js").read_text(encoding="utf-8")
        self.assertIn('/api/models/catalog?${systemParams.toString()}', module)
        self.assertIn('/models/catalog?${projectParams.toString()}', module)
        self.assertIn("const ranked = new Map", module)
        self.assertIn('/compare/runs?architecture=', module)
        self.assertIn("initModelGuide();", registry)
        self.assertIn("renderModelGuidePage();", registry)

    def test_model_report_preview_and_exports_are_functional(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        module = (ROOT / "static" / "pages" / "model_guide.js").read_text(encoding="utf-8")
        for output in ("markdown", "html", "pdf"):
            self.assertIn(f'data-model-guide-export="{output}"', html)
        self.assertIn("function buildReport()", module)
        self.assertIn("function reportMarkdown(report)", module)
        self.assertIn("function reportHtml(report, markdown)", module)
        self.assertIn("printWindow.print();", module)
        self.assertIn("printWindow.opener = null", module)
        self.assertNotIn("button.disabled = !guideState.report", module)
        self.assertIn("document.body.appendChild(link)", module)
        self.assertIn("link.remove()", module)
        self.assertIn('t("modelGuide.reportSourceNote")', module)

    def test_model_guide_has_dedicated_responsive_styles(self):
        css = (ROOT / "static" / "styles" / "pages" / "model_guide.css").read_text(encoding="utf-8")
        self.assertIn(".model-guide-workspace", css)
        self.assertIn("grid-template-columns: minmax(250px, 28%)", css)
        self.assertIn("@media (max-width: 800px)", css)

    def test_task_selector_explains_classifier_and_regressor_outputs(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        module = (ROOT / "static" / "pages" / "model_guide.js").read_text(encoding="utf-8")
        zh_tw = (ROOT / "static" / "state" / "i18n" / "zh-TW.js").read_text(encoding="utf-8")
        self.assertIn('id="model-guide-task-explainer"', html)
        self.assertIn('data-i18n="modelGuide.classificationChoice"', html)
        self.assertIn('data-i18n="modelGuide.regressionChoice"', html)
        self.assertIn("function renderTaskExplainer()", module)
        self.assertIn('"modelGuide.classificationDescription"', zh_tw)
        self.assertIn('"modelGuide.regressionDescription"', zh_tw)

    def test_i18n_audit_distinguishes_technical_identifiers(self):
        audit = (ROOT / "scripts" / "i18n_dom_audit.mjs").read_text(encoding="utf-8")
        self.assertIn('parent.closest(".no-i18n, [data-i18n-ignore]")', audit)
        self.assertIn('element.closest(".no-i18n, [data-i18n-ignore]")', audit)


if __name__ == "__main__":
    unittest.main()
