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

    def test_history_uses_rnn_specific_project_metrics(self):
        projects_js = (ROOT / "static" / "pages" / "projects.js").read_text(encoding="utf-8")

        self.assertIn("function renderRnnProjectFileSummary", projects_js)
        self.assertIn('fileMetric("Target / Y"', projects_js)
        self.assertIn('fileMetric("Features / X"', projects_js)
        self.assertIn('fileMetric("Runs"', projects_js)
        self.assertIn("function renderCnnProjectFileSummary", projects_js)

    def test_inference_cleanup_toolbar_is_hidden_when_no_jobs_exist(self):
        projects_js = (ROOT / "static" / "pages" / "projects.js").read_text(encoding="utf-8")

        self.assertIn("const shouldShowJobSection = inferenceHistoryLoading", projects_js)
        self.assertIn("if (!shouldShowJobSection) return projectHtml;", projects_js)


if __name__ == "__main__":
    unittest.main()
