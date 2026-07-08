import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UIHardeningPhasesStaticTests(unittest.TestCase):
    def read(self, *parts):
        return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")

    def test_phase2_structured_api_error_frontend_contract(self):
        api_js = self.read("static", "api.js")
        toast_js = self.read("static", "core", "toast.js")
        self.assertIn("export class VtsApiError", api_js)
        self.assertIn("normalizeApiErrorPayload", api_js)
        self.assertIn("formatApiErrorForToast", api_js)
        self.assertIn("fieldErrors", api_js)
        self.assertIn("suggestion", api_js)
        self.assertIn("toast-${severity}", toast_js)
        self.assertNotIn("data.detail || JSON.stringify(data)", api_js)

    def test_phase3_dirty_and_stale_state_are_visible(self):
        dirty_js = self.read("static", "core", "dirty_forms.js")
        stale_js = self.read("static", "core", "resource_freshness.js")
        bootstrap_js = self.read("static", "core", "bootstrap.js")
        dashboard_js = self.read("static", "pages", "dashboard.js")
        self.assertIn("registerDirtyForm", dirty_js)
        self.assertIn("beforeunload", dirty_js)
        self.assertIn("markResourceStaleFromRequest", stale_js)
        self.assertIn("initDirtyFormTracking();", bootstrap_js)
        self.assertIn("initResourceFreshnessTracking();", bootstrap_js)
        self.assertIn('data-ui-smoke="dirty-form-alert"', dashboard_js)
        self.assertIn('data-ui-smoke="stale-resource-alert"', dashboard_js)

    def test_phase4_cnn_guided_wizard_is_connected_to_dashboard(self):
        wizard_js = self.read("static", "core", "cnn_guided_wizard.js")
        dashboard_js = self.read("static", "pages", "dashboard.js")
        dashboard_css = self.read("static", "styles", "pages", "dashboard.css")
        self.assertIn("buildCnnGuidedWizard", wizard_js)
        self.assertIn("renderCnnGuidedWizard", wizard_js)
        self.assertIn('data-ui-smoke="cnn-guided-wizard"', wizard_js)
        self.assertIn("buildCnnGuidedWizard(status, appState)", dashboard_js)
        self.assertIn("workflow-map-details", dashboard_js)
        self.assertIn("Detailed Workflow Map", dashboard_js)
        self.assertIn("guided-step-grid", dashboard_css)
        self.assertIn(".workflow-map-details", dashboard_css)
        self.assertIn(".workflow-map-summary", dashboard_css)

    def test_phase5_deployment_decision_card_is_connected_to_compare(self):
        decision_js = self.read("static", "core", "deployment_decision.js")
        compare_js = self.read("static", "pages", "model_compare.js")
        compare_css = self.read("static", "styles", "pages", "model_compare.css")
        self.assertIn("buildDeploymentDecision", decision_js)
        self.assertIn("renderDeploymentDecisionCard", decision_js)
        self.assertIn('data-ui-smoke="deployment-decision-card"', decision_js)
        self.assertIn("buildDeploymentDecision(compareState.result)", compare_js)
        self.assertIn("renderDeploymentDecisionCard(decision)", compare_js)
        self.assertIn(".deployment-decision-card", compare_css)

    def test_phase6_design_system_and_smoke_contract_exist(self):
        style_css = self.read("static", "style.css")
        design_doc = self.read("docs", "UI_DESIGN_SYSTEM.md")
        spec = self.read("packaging", "vision_training_studio.spec")
        self.assertIn('@import "./styles/tokens.css";', style_css)
        self.assertIn('@import "./styles/components.css";', style_css)
        self.assertIn('@import "./styles/pages/dashboard.css";', style_css)
        self.assertIn('docs" / "UI_DESIGN_SYSTEM.md"', spec)
        self.assertIn("UI Smoke Contract", design_doc)
        self.assertIn("data-ui-smoke", design_doc)
        self.assertIn("Deployment Decision", design_doc)


if __name__ == "__main__":
    unittest.main()
