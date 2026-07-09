import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProjectAssistantPositioningStaticTests(unittest.TestCase):
    def test_project_assistant_is_contextual_not_primary_navigation(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        sidebar = html.split('<aside class="sidebar">', 1)[1].split("</aside>", 1)[0]
        header = html.split('<header class="top-header">', 1)[1].split("</header>", 1)[0]

        self.assertIn('id="btn-project-assistant"', header)
        self.assertIn('data-nav="project-assistant"', header)
        self.assertNotIn("project-assistant", sidebar)
        self.assertNotIn("rag-workbench", sidebar)
        self.assertNotIn("Project Assistant", sidebar)

    def test_visible_product_copy_does_not_present_rag_workbench(self):
        visible_files = [
            ROOT / "static" / "index.html",
            ROOT / "static" / "state" / "i18n" / "en.js",
            ROOT / "static" / "state" / "i18n" / "zh-TW.js",
            ROOT / "static" / "pages" / "project_assistant_impl.js",
            ROOT / "static" / "core" / "right_panel.js",
        ]
        forbidden = [
            "RAG Workbench",
            "Retrieval Workbench",
            "RAG artifact",
            "RAG answer",
        ]

        for path in visible_files:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                for phrase in forbidden:
                    self.assertNotIn(phrase, text)

    def test_frontend_uses_primary_project_assistant_contract(self):
        registry = (ROOT / "static" / "core" / "page_registry.js").read_text(encoding="utf-8")
        router = (ROOT / "static" / "core" / "router.js").read_text(encoding="utf-8")
        impl = (ROOT / "static" / "pages" / "project_assistant_impl.js").read_text(encoding="utf-8")
        legacy = (ROOT / "static" / "pages" / "rag_workbench.js").read_text(encoding="utf-8")

        self.assertIn("../pages/project_assistant.js", registry)
        self.assertNotIn("../pages/rag_workbench.js", registry)
        self.assertIn('"rag-workbench": "project-assistant"', router)
        self.assertIn("/api/project-assistant", impl)
        self.assertNotIn("/api/rag-workbench", impl)
        self.assertIn("initProjectAssistantImpl as initRagWorkbench", legacy)

    def test_legacy_backend_routes_are_explicit_compatibility_only(self):
        legacy_route = (ROOT / "src" / "api" / "routes" / "rag_workbench.py").read_text(encoding="utf-8")
        legacy_service = (ROOT / "src" / "rag_workbench.py").read_text(encoding="utf-8")

        self.assertIn("Backward-compatible route module only", legacy_route)
        self.assertIn("src.api.routes.project_assistant", legacy_route)
        self.assertIn("Backward-compatible import alias only", legacy_service)
        self.assertIn("RagWorkbenchService = ProjectAssistantService", legacy_service)


if __name__ == "__main__":
    unittest.main()
