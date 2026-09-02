import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkspaceDataIsolationStaticTests(unittest.TestCase):
    def test_workspace_routes_do_not_cross_data_preparation_boundaries(self):
        modes = (ROOT / "static" / "pages" / "training_modes.js").read_text(encoding="utf-8")
        index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

        for page in ('"dataset"', '"labelme"', '"split"', '"augmentation"'):
            self.assertIn(page, modes)
        self.assertIn("TABULAR_INCOMPATIBLE_PAGES.has(page)", modes)
        self.assertIn("RNN_INCOMPATIBLE_PAGES.has(page)", modes)
        self.assertIn('mode === "cnn" && page === "tabular"', modes)

        self.assertIn('data-rnn-nav="windowing"', index)
        self.assertIn('id="rnn-sequence-length"', index)
        self.assertIn('id="rnn-stride"', index)
        self.assertIn('id="rnn-horizon"', index)
        self.assertIn('id="tabular-workspace-root"', index)
        self.assertIn('id="page-labelme"', index)

    def test_feature_importance_is_evaluation_not_data_preparation(self):
        tabular = (ROOT / "static" / "pages" / "tabular.js").read_text(encoding="utf-8")
        evaluation = (ROOT / "static" / "pages" / "evaluation.js").read_text(encoding="utf-8")

        self.assertNotIn("function renderFeatureImportance", tabular)
        self.assertIn("function renderFeatureImportance", evaluation)


if __name__ == "__main__":
    unittest.main()
