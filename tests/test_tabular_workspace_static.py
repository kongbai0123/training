import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TabularWorkspaceStaticTests(unittest.TestCase):
    def read(self, *parts: str) -> str:
        return ROOT.joinpath(*parts).read_text(encoding="utf-8")

    def test_tabular_is_an_independent_project_and_workspace_mode(self):
        index_html = self.read("static", "index.html")
        projects = self.read("static", "pages", "projects.js")
        modes = self.read("static", "pages", "training_modes.js")
        registry = self.read("static", "core", "page_registry.js")

        self.assertIn('value="tabular_classification"', index_html)
        self.assertIn('value="tabular_regression"', index_html)
        self.assertIn('id="page-tabular"', index_html)
        self.assertIn('id="tabular-workspace-root"', index_html)
        self.assertIn('data-tabular-nav="overview"', index_html)
        self.assertIn('data-tabular-nav="registry"', index_html)
        self.assertIn('data-tabular-nav="evaluation" data-page="evaluation"', index_html)
        self.assertIn('data-project-mode="tabular"', index_html)
        self.assertIn('tabular_classification:', projects)
        self.assertIn('tabular_regression:', projects)
        self.assertIn('["cnn", "rnn", "tabular"]', modes)
        self.assertIn('if (mode === "tabular") eventBus.emit("navigate", "tabular")', modes)
        self.assertIn("const RNN_INCOMPATIBLE_PAGES", modes)
        self.assertIn('mode === "rnn" && (page === "tabular" || RNN_INCOMPATIBLE_PAGES.has(page))', modes)
        self.assertIn('initTabularWorkspace', registry)
        self.assertIn('renderTabularWorkspace', registry)

    def test_workspace_exposes_the_complete_xgboost_production_loop(self):
        tabular = self.read("static", "pages", "tabular.js")
        compare = self.read("static", "pages", "model_compare.js")

        for endpoint in (
            "/tabular/workspace",
            "/tabular/config",
            "/tabular/dataset/import",
            "/tabular/inference/row",
            "/tabular/inference/batch",
            "/models/versions",
            "/models/${encodeURIComponent(modelId)}/lifecycle",
            "/export/jobs?",
        ):
            self.assertIn(endpoint, tabular)

        for action in (
            'data-tabular-action="import-dataset"',
            'data-tabular-action="infer-row"',
            'data-tabular-action="infer-batch"',
            'data-tabular-action="lifecycle"',
            'data-tabular-action="export"',
        ):
            self.assertIn(action, tabular)

        evaluation = self.read("static", "pages", "evaluation.js")
        self.assertNotIn("function renderFeatureImportance", tabular)
        self.assertIn("function renderFeatureImportance", evaluation)
        self.assertIn('backend: "xgboost_tabular"', tabular)
        self.assertIn('architecture: "tabular"', tabular)
        self.assertIn('artifactRole === "best"', tabular)
        self.assertIn("function normalizeVersions(payload)", tabular)
        self.assertIn("function normalizeExports(payload)", tabular)
        self.assertIn("/compare/runs?architecture=${encodeURIComponent(compareState.architecture)}", compare)
        self.assertIn('"tabular"', compare)

    def test_tabular_assets_have_a_shared_cache_marker(self):
        index_html = self.read("static", "index.html")
        app_js = self.read("static", "app.js")
        bootstrap = self.read("static", "core", "bootstrap.js")
        page_registry = self.read("static", "core", "page_registry.js")

        self.assertIn("style.css?v=20260902-unified-evaluation", index_html)
        self.assertIn("app.js?v=20260902-unified-evaluation", index_html)
        self.assertIn("bootstrap.js?v=20260902-unified-evaluation", app_js)
        self.assertIn("page_registry.js?v=20260902-unified-evaluation", bootstrap)
        self.assertIn("training_modes.js?v=20260902-unified-evaluation", page_registry)
        self.assertIn("tabular.js?v=20260825-tabular-mvp", page_registry)


if __name__ == "__main__":
    unittest.main()
