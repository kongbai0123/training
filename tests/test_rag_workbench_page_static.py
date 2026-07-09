import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RagWorkbenchPageStaticTests(unittest.TestCase):
    def test_rag_workbench_navigation_and_page_shell_exist(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

        self.assertIn('data-page="rag-workbench"', html)
        self.assertIn('id="page-rag-workbench"', html)
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
        registry = (ROOT / "static" / "core" / "page_registry.js").read_text(encoding="utf-8")
        module = (ROOT / "static" / "pages" / "rag_workbench.js").read_text(encoding="utf-8")

        self.assertIn('navigate(params.get("page") || "dashboard")', bootstrap)
        self.assertIn("initRagWorkbench", registry)
        self.assertIn("renderRagWorkbenchPage", registry)
        self.assertIn("/api/rag-workbench/status", module)
        self.assertIn("/api/rag-workbench/knowledge-base/documents", module)
        self.assertIn("/api/rag-workbench/knowledge-base/upload", module)
        self.assertIn("/api/rag-workbench/retrieval/query", module)
        self.assertIn("/api/rag-workbench/chat", module)
        self.assertIn("/api/rag-workbench/sandbox/files", module)
        self.assertIn("/api/rag-workbench/evaluation/report", module)
        self.assertIn("conversation_state: ragState.conversationState", module)

    def test_rag_workbench_i18n_and_css_are_wired(self):
        style = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
        css = (ROOT / "static" / "styles" / "pages" / "rag_workbench.css").read_text(encoding="utf-8")
        en = (ROOT / "static" / "state" / "i18n" / "en.js").read_text(encoding="utf-8")
        zh = (ROOT / "static" / "state" / "i18n" / "zh-TW.js").read_text(encoding="utf-8")

        self.assertIn('styles/pages/rag_workbench.css', style)
        self.assertIn(".rag-workbench-grid", css)
        self.assertIn("@media (max-width: 1200px)", css)
        self.assertIn('"rag.title"', en)
        self.assertIn('"rag.title"', zh)
        self.assertIn('"rag.noRawThought"', en)
        self.assertIn('"rag.noRawThought"', zh)
        self.assertIn('"rag.uploadFile"', en)
        self.assertIn('"rag.uploadFile"', zh)


if __name__ == "__main__":
    unittest.main()
