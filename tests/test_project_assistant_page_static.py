import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProjectAssistantPageStaticTests(unittest.TestCase):
    def test_project_assistant_is_not_primary_sidebar_navigation(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

        self.assertNotIn('data-page="rag-workbench"', html)
        self.assertNotIn('id="page-rag-workbench"', html)
        self.assertIn('id="btn-project-assistant"', html)
        self.assertIn('data-nav="project-assistant"', html)
        self.assertIn('id="section-project-assistant-context"', html)
        self.assertIn('id="btn-project-assistant-sync-context"', html)
        self.assertIn('id="page-project-assistant"', html)
        self.assertIn('id="rag-status-model"', html)
        self.assertIn('id="rag-document-list"', html)
        self.assertIn('id="rag-upload-file"', html)
        self.assertIn('id="btn-rag-upload"', html)
        self.assertIn('id="btn-rag-sync-artifacts"', html)
        self.assertIn('id="rag-retrieval-results"', html)
        self.assertIn('id="rag-chat-sources"', html)
        self.assertIn('id="rag-agent-trace"', html)
        self.assertIn('id="rag-sandbox-preview"', html)
        self.assertIn('id="rag-evaluation-summary"', html)
        project_assistant_fragment = html.split('<section class="page" id="page-project-assistant">', 1)[1].split('<section class="page"', 1)[0]
        self.assertNotIn(">RAG<", project_assistant_fragment)
        self.assertNotIn("No RAG answer yet.", project_assistant_fragment)
        self.assertNotIn("RAG artifact preview", project_assistant_fragment)
        self.assertNotIn("Retrieval Workbench", project_assistant_fragment)

    def test_project_assistant_module_is_registered_and_calls_contract_apis(self):
        bootstrap = (ROOT / "static" / "core" / "bootstrap.js").read_text(encoding="utf-8")
        router = (ROOT / "static" / "core" / "router.js").read_text(encoding="utf-8")
        registry = (ROOT / "static" / "core" / "page_registry.js").read_text(encoding="utf-8")
        project_assistant_module = (ROOT / "static" / "pages" / "project_assistant.js").read_text(encoding="utf-8")
        legacy_module = (ROOT / "static" / "pages" / "rag_workbench.js").read_text(encoding="utf-8")
        module = (ROOT / "static" / "pages" / "project_assistant_impl.js").read_text(encoding="utf-8")

        self.assertIn('navigate(params.get("page") || "dashboard")', bootstrap)
        self.assertIn("initProjectAssistant", registry)
        self.assertIn("renderProjectAssistantPage", registry)
        self.assertIn("initProjectAssistantImpl as initProjectAssistant", project_assistant_module)
        self.assertIn("initProjectAssistantImpl as initRagWorkbench", legacy_module)
        self.assertIn('"rag-workbench": "project-assistant"', router)
        self.assertIn("/api/project-assistant", module)
        self.assertIn('assistantApi("/settings")', module)
        self.assertIn("/sync-artifacts", module)
        self.assertNotIn("/api/rag-workbench", module)
        self.assertIn("project_id", module)
        self.assertIn("conversation_state: assistantState.conversationState", module)

    def test_project_assistant_i18n_and_legacy_css_are_wired(self):
        style = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
        css = (ROOT / "static" / "styles" / "pages" / "project_assistant.css").read_text(encoding="utf-8")
        en = (ROOT / "static" / "state" / "i18n" / "en.js").read_text(encoding="utf-8")
        zh = (ROOT / "static" / "state" / "i18n" / "zh-TW.js").read_text(encoding="utf-8")

        self.assertIn('styles/pages/project_assistant.css', style)
        self.assertNotIn('styles/pages/rag_workbench.css', style)
        self.assertIn(".project-assistant-grid", css)
        self.assertNotIn(".rag-workbench-grid", css)
        self.assertIn("@media (max-width: 1200px)", css)
        self.assertIn('"projectAssistant.open"', en)
        self.assertIn('"projectAssistant.open"', zh)
        self.assertIn('"projectAssistant.syncArtifacts"', en)
        self.assertIn('"projectAssistant.syncArtifacts"', zh)
        self.assertIn('id="rag-settings-mode"', (ROOT / "static" / "index.html").read_text(encoding="utf-8"))
        self.assertIn('"rag.settings.mode.localSearch"', en)
        self.assertIn('"rag.settings.mode.localSearch"', zh)
        self.assertIn('"rag.title"', en)
        self.assertIn('"rag.title"', zh)
        self.assertIn('"rag.noRawThought"', en)
        self.assertIn('"rag.noRawThought"', zh)
        self.assertIn('"rag.uploadFile"', en)
        self.assertIn('"rag.uploadFile"', zh)
        self.assertIn('"rag.syncArtifacts"', en)
        self.assertIn('"rag.syncArtifacts"', zh)
        self.assertNotIn('"rag.mode": "Mode"', en)
        self.assertNotIn("RAG answer", en)
        self.assertNotIn("RAG artifact", en)

    def test_project_assistant_product_plan_replaces_rag_workbench_plan(self):
        plan_path = ROOT / "docs" / "PROJECT_ASSISTANT_UX_PLAN.md"
        self.assertTrue(plan_path.exists())
        self.assertFalse((ROOT / "docs" / "RAG_WORKBENCH_UX_PLAN.md").exists())
        plan = plan_path.read_text(encoding="utf-8")

        self.assertIn("Vision Training Studio is not a RAG product", plan)
        self.assertIn("Project Assistant is an auxiliary layer", plan)
        self.assertIn("tests/test_project_assistant_contract.py", plan)
        self.assertIn("tests/test_project_assistant_page_static.py", plan)
        self.assertNotIn("tests/test_rag_workbench_contract.py", plan)
        self.assertNotIn("tests/test_rag_workbench_page_static.py", plan)
        self.assertIn("Legacy compatibility components", plan)
        self.assertIn("Visible UI copy no longer presents this as RAG Workbench", plan)

    def test_project_assistant_context_is_available_on_decision_pages(self):
        right_panel = (ROOT / "static" / "core" / "right_panel.js").read_text(encoding="utf-8")
        layout_css = (ROOT / "static" / "styles" / "layout.css").read_text(encoding="utf-8")

        self.assertIn("renderProjectAssistantContext", right_panel)
        self.assertIn("buildProjectAssistantContext", right_panel)
        self.assertIn("dashboard:", right_panel)
        self.assertIn("evaluation:", right_panel)
        self.assertIn('"model-compare":', right_panel)
        self.assertIn("export:", right_panel)
        self.assertIn("history:", right_panel)
        self.assertIn("Evidence", right_panel)
        self.assertIn("Suggested questions", right_panel)
        self.assertIn("syncProjectAssistantContextArtifacts", right_panel)
        self.assertIn("/sync-artifacts", right_panel)
        self.assertIn("Metric decisions still come from deterministic evaluation.", right_panel)
        self.assertIn("compare table remains the source of truth", right_panel)
        self.assertIn("Explain the export package", right_panel)
        self.assertIn("Summarize the current", right_panel)
        self.assertIn(".assistant-context-group", layout_css)


if __name__ == "__main__":
    unittest.main()
