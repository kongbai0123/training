import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ExportPageStaticTests(unittest.TestCase):
    def test_export_page_has_task_aware_action_groups(self):
        index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        export_js = (ROOT / "static" / "pages" / "export.js").read_text(encoding="utf-8")
        page_registry_js = (ROOT / "static" / "core" / "page_registry.js").read_text(encoding="utf-8")

        self.assertIn('id="export-cnn-actions"', index_html)
        self.assertIn('id="export-rnn-actions" hidden', index_html)
        self.assertIn("export-selector-grid", index_html)
        self.assertIn("export-model-selector-card", index_html)
        self.assertIn("export-model-toolbar", index_html)
        self.assertIn('data-export-format="onnx"', index_html)
        self.assertIn('id="export-onnx-precision"', index_html)
        self.assertIn('<option value="fp16">FP16</option>', index_html)
        self.assertIn('<option value="int8" disabled', index_html)
        self.assertIn('data-export-format="pt"', index_html)
        self.assertIn('data-export-format="rnn_package"', index_html)
        self.assertIn('data-export-format="rnn_contract"', index_html)
        self.assertIn('data-export-format="rnn_schema_scaler"', index_html)
        self.assertIn('id="export-result-panel"', index_html)
        self.assertIn('id="export-artifact-list"', index_html)
        self.assertIn('import { initExport, renderExportPage } from "../pages/export.js?v=20260711-layout-export-precision";', page_registry_js)
        self.assertIn("function isRnnProject(project)", export_js)
        self.assertIn("cnnActions.hidden = isRnn", export_js)
        self.assertIn("rnnActions.hidden = !isRnn", export_js)
        self.assertIn('params.set("format", format)', export_js)
        self.assertIn("loadExportArtifacts", export_js)
        self.assertIn("renderExportArtifactList", export_js)

    def test_export_layout_hides_inactive_action_group_and_bottom_aligns_buttons(self):
        base_css = (ROOT / "static" / "styles" / "base.css").read_text(encoding="utf-8")
        components_css = (ROOT / "static" / "styles" / "components.css").read_text(encoding="utf-8")

        self.assertIn("[hidden]", base_css)
        self.assertIn("display: none !important;", base_css)
        self.assertIn("#page-export .export-model-selector-card", components_css)
        self.assertIn("#page-export .export-model-toolbar", components_css)
        self.assertIn("#page-export #export-cnn-actions", components_css)
        self.assertIn(".export-result-panel", components_css)
        self.assertIn(".export-artifact-row", components_css)
        self.assertIn("margin-top: auto;", components_css)
        self.assertIn("justify-content: center;", components_css)

    def test_rnn_workspace_export_panel_is_operational(self):
        index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        training_modes_js = (ROOT / "static" / "pages" / "training_modes.js").read_text(encoding="utf-8")
        page_registry_js = (ROOT / "static" / "core" / "page_registry.js").read_text(encoding="utf-8")

        self.assertIn('id="rnn-export-model"', index_html)
        self.assertIn('id="rnn-refresh-export-models"', index_html)
        self.assertIn('data-rnn-export-format="rnn_package"', index_html)
        self.assertIn('data-rnn-export-format="rnn_contract"', index_html)
        self.assertIn('data-rnn-export-format="rnn_schema_scaler"', index_html)
        self.assertIn('id="rnn-export-result"', index_html)
        self.assertIn('id="rnn-export-artifact-list"', index_html)
        self.assertIn("loadRnnExportModels({ force: true })", training_modes_js)
        self.assertIn("loadRnnExportArtifacts", training_modes_js)
        self.assertIn("async function exportRnnArtifact", training_modes_js)
        self.assertIn("params.set(\"model_id\", selectedModelId)", training_modes_js)
        self.assertIn("resolveExportPath(data)", training_modes_js)
        self.assertIn("../pages/training_modes.js?v=20260716-rnn-monitor-intelligence", page_registry_js)


if __name__ == "__main__":
    unittest.main()
