import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class NavigationLifecycleStaticTests(unittest.TestCase):
    def test_only_the_active_secondary_page_is_rendered(self):
        registry = (ROOT / "static" / "core" / "page_registry.js").read_text(encoding="utf-8")

        self.assertIn("const renderActivePage = {", registry)
        self.assertIn("}[appState.currentPage]", registry)
        self.assertIn("renderActivePage?.();", registry)
        self.assertNotIn("\n  renderDatasetPage(status);\n  renderLabelMeManager(status);", registry)

    def test_rnn_navigation_reuses_loaded_project_state(self):
        modes = (ROOT / "static" / "pages" / "training_modes.js").read_text(encoding="utf-8")
        state = (ROOT / "static" / "pages" / "training_mode_state.js").read_text(encoding="utf-8")

        self.assertIn('configProjectId: ""', state)
        self.assertIn('readinessKey: ""', state)
        self.assertIn("if (!projectChanged && trainingModeState.rnn.config && !options.force)", modes)
        self.assertIn("trainingModeState.rnn.readinessKey === readinessKey", modes)
        self.assertNotIn("loadRnnConfig({ force: true });", modes)

    def test_empty_results_are_cached_until_project_refresh(self):
        modes = (ROOT / "static" / "pages" / "training_modes.js").read_text(encoding="utf-8")
        training = (ROOT / "static" / "pages" / "training.js").read_text(encoding="utf-8")
        evaluation = (ROOT / "static" / "pages" / "evaluation.js").read_text(encoding="utf-8")

        self.assertIn("trainingModeState.rnn.evaluationLoaded", modes)
        self.assertIn("trainingModeState.rnn.exportLoaded", modes)
        self.assertIn("trainingModeState.rnn.inferenceModelsLoaded", modes)
        self.assertIn("trainingModeState.rnn.inferenceResultLoaded", modes)
        self.assertIn("emptyRunListProjectId === appState.currentProjectId", training)
        self.assertIn("loadedEvaluationProjectId === appState.currentProjectId", evaluation)

    def test_reads_are_deduplicated_and_background_progress_is_silent(self):
        api = (ROOT / "static" / "api.js").read_text(encoding="utf-8")
        progress = (ROOT / "static" / "core" / "task_progress.js").read_text(encoding="utf-8")

        self.assertIn("const inflightReads = new Map();", api)
        self.assertIn("inflightReads.has(key)", api)
        self.assertIn("responseCacheTtlMs", api)
        self.assertIn('options.progressMode !== "foreground"', progress)
        self.assertIn("if (isBackgroundRead) return null;", progress)


if __name__ == "__main__":
    unittest.main()
