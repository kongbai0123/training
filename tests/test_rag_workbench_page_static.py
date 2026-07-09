import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RagWorkbenchPageStaticTests(unittest.TestCase):
    def test_project_assistant_is_not_primary_sidebar_navigation(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

        self.assertNotIn('data-page="rag-workbench"', html)
        self.assertNotIn('id="page-rag-workbench"', html)
        self.assertIn('id="btn-project-assistant"', html)
        self.assertIn('data-nav="project-assistant"', html)
        self.assertIn('id="section-project-assistant-context"', html)
        self.assertIn('id="page-project-assistant"', html)
        self.assertIn('id="rag-status-model"', html)
        self.assertIn('id="rag-document-list"', html)
        self.assertIn('id="rag-upload-file"', html)
        self.assertIn('id="btn-rag-upload"', html)
        self.assertIn('id="rag-retrieval-results"', html)
        self.assertIn('id="rag-chat-sources"', html)
        self.assertIn('id="rag-agent-trace"', html)
        self.assertIn('id="rag-sandbox-preview"', html)
        self.assertIn('id="rag-evaluation-summary"', html)

    def test_rag_workbench_module_is_registered_and_calls_contract_apis(self):
        bootstrap = (ROOT / "static" / "core" / "bootstrap.js").read_text(encoding="utf-8")
        router = (ROOT / "static" / "core" / "router.js").read_text(encoding="utf-8")
        registry = (ROOT / "static" / "core" / "page_registry.js").read_text(encoding="utf-8")
        project_assistant_module = (ROOT / "static" / "pages" / "project_assistant.js").read_text(encoding="utf-8")
        module = (ROOT / "static" / "pages" / "rag_workbench.js").read_text(encoding="utf-8")

        self.assertIn('navigate(params.get("page") || "dashboard")', bootstrap)
        self.assertIn("initProjectAssistant", registry)
        self.assertIn("renderProjectAssistantPage", registry)
        self.assertIn("initRagWorkbench as initProjectAssistant", project_assistant_module)
        self.assertIn('"rag-workbench": "project-assistant"', router)
        self.assertIn("/api/project-assistant", module)
        self.assertIn('assistantApi("/settings")', module)
        self.assertNotIn("/api/rag-workbench", module)
        self.assertIn("project_id", module)
        self.assertIn("conversation_state: ragState.conversationState", module)

    def test_rag_workbench_i18n_and_css_are_wired(self):
        style = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
        css = (ROOT / "static" / "styles" / "pages" / "rag_workbench.css").read_text(encoding="utf-8")
        en = (ROOT / "static" / "state" / "i18n" / "en.js").read_text(encoding="utf-8")
        zh = (ROOT / "static" / "state" / "i18n" / "zh-TW.js").read_text(encoding="utf-8")

        self.assertIn('styles/pages/rag_workbench.css', style)
        self.assertIn(".rag-workbench-grid", css)
        self.assertIn("@media (max-width: 1200px)", css)
        self.assertIn('"projectAssistant.open"', en)
        self.assertIn('"projectAssistant.open"', zh)
        self.assertIn('id="rag-settings-mode"', (ROOT / "static" / "index.html").read_text(encoding="utf-8"))
        self.assertIn('"rag.settings.mode.localSearch"', en)
        self.assertIn('"rag.settings.mode.localSearch"', zh)
        self.assertIn('"rag.title"', en)
        self.assertIn('"rag.title"', zh)
        self.assertIn('"rag.noRawThought"', en)
        self.assertIn('"rag.noRawThought"', zh)
        self.assertIn('"rag.uploadFile"', en)
        self.assertIn('"rag.uploadFile"', zh)

    def test_project_assistant_context_is_available_on_decision_pages(self):
        right_panel = (ROOT / "static" / "core" / "right_panel.js").read_text(encoding="utf-8")

        self.assertIn("renderProjectAssistantContext", right_panel)
        self.assertIn("buildProjectAssistantContext", right_panel)
        self.assertIn("evaluation:", right_panel)
        self.assertIn('"model-compare":', right_panel)
        self.assertIn("export:", right_panel)
        self.assertIn("history:", right_panel)
        self.assertIn("Use the assistant to explain metrics", right_panel)


if __name__ == "__main__":
    unittest.main()
