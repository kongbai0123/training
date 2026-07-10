import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProjectsPageStaticTests(unittest.TestCase):
    def test_rnn_project_creation_hides_cnn_class_list(self):
        projects_js = (ROOT / "static" / "pages" / "projects.js").read_text(encoding="utf-8")

        self.assertIn('classField?.classList.toggle("hidden", isSequence)', projects_js)
        self.assertIn('classList?.classList.toggle("hidden", isSequence)', projects_js)
        self.assertIn('const classes = isSequence ? [] : [...appState.newProjectClasses];', projects_js)
        self.assertIn('input.disabled = isSequence;', projects_js)
        self.assertNotIn('isSequence ? "Target labels" : "Class list"', projects_js)
        self.assertIn('if (event.key !== "Enter") return;', projects_js)
        self.assertNotIn('["Enter", ",", ";"].includes(event.key)', projects_js)

    def test_history_uses_rnn_specific_project_metrics(self):
        projects_js = (ROOT / "static" / "pages" / "projects.js").read_text(encoding="utf-8")

        self.assertIn("function renderRnnProjectFileSummary", projects_js)
        self.assertIn('if (isRnnTask) return "rnn";', projects_js)
        self.assertNotIn('return "CNN/RNN"', projects_js)
        self.assertNotIn("files.best_weights || 0) > 0 ||", projects_js)
        self.assertNotIn("files.last_weights || 0) > 0 ||", projects_js)
        self.assertIn('fileMetric("Target / Y"', projects_js)
        self.assertIn('fileMetric("Features / X"', projects_js)
        self.assertIn('fileMetric("Runs"', projects_js)
        self.assertIn("function renderCnnProjectFileSummary", projects_js)

    def test_inference_cleanup_toolbar_is_hidden_when_no_jobs_exist(self):
        projects_js = (ROOT / "static" / "pages" / "projects.js").read_text(encoding="utf-8")

        self.assertIn("const shouldShowJobSection = inferenceHistoryLoading", projects_js)
        self.assertIn("if (!shouldShowJobSection) return projectHtml;", projects_js)

    def test_projects_module_cache_busts_history_family_fix(self):
        page_registry_js = (ROOT / "static" / "core" / "page_registry.js").read_text(encoding="utf-8")
        app_js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

        self.assertIn("../pages/projects.js?v=20260709-project-open-delegation", page_registry_js)
        self.assertIn("./core/bootstrap.js?v=20260709-rnn-export-workbench", app_js)
        self.assertIn("/static/app.js?v=20260709-rnn-export-workbench", index_html)


if __name__ == "__main__":
    unittest.main()
