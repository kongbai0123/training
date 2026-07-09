from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AutoLabelingPageStaticTests(unittest.TestCase):
    def test_source_drop_zone_is_enabled_and_connected_to_dataset_import_apis(self):
        index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        auto_labeling_js = (ROOT / "static" / "pages" / "auto_labeling.js").read_text(encoding="utf-8")
        utils_js = (ROOT / "static" / "utils.js").read_text(encoding="utf-8")

        self.assertIn('id="auto-source-drop-zone"', index_html)
        self.assertNotIn("disabled-drop source-drop-preview", index_html)
        self.assertNotIn("拖曳會在 upload / folder scan API 接入後啟用", index_html)
        self.assertIn("collectDroppedFiles", auto_labeling_js)
        self.assertIn("webkitGetAsEntry", utils_js)
        self.assertIn("readEntries", utils_js)
        self.assertIn("/upload-images", auto_labeling_js)
        self.assertIn("/import-zip", auto_labeling_js)

    def test_source_drop_zone_classifies_folder_file_extensions_before_upload(self):
        auto_labeling_js = (ROOT / "static" / "pages" / "auto_labeling.js").read_text(encoding="utf-8")

        self.assertIn("export function classifyAutoLabelSourceFiles(files)", auto_labeling_js)
        self.assertIn("file?.webkitRelativePath || file?.name", auto_labeling_js)
        self.assertIn('new Set([".jpg", ".jpeg", ".png", ".bmp"])', auto_labeling_js)
        self.assertIn('new Set([".zip"])', auto_labeling_js)
        self.assertIn("const classified = classifyAutoLabelSourceFiles(allFiles)", auto_labeling_js)
        self.assertIn("classified.images", auto_labeling_js)
        self.assertIn("classified.zips", auto_labeling_js)
        self.assertIn("classified.rejected.length", auto_labeling_js)

    def test_auto_labeling_module_uses_cache_busted_import(self):
        page_registry_js = (ROOT / "static" / "core" / "page_registry.js").read_text(encoding="utf-8")

        self.assertIn(
            "./pages/auto_labeling.js?v=20260709-review-gate",
            page_registry_js,
        )

    def test_training_mode_sidebar_is_initialized_for_cnn_page_navigation(self):
        page_registry_js = (ROOT / "static" / "core" / "page_registry.js").read_text(encoding="utf-8")

        self.assertIn("initTrainingModeSidebar", page_registry_js)
        self.assertIn("initTrainingModeSidebar();", page_registry_js)
        self.assertIn("renderTrainingModeSidebar", page_registry_js)

    def test_auto_labeling_layout_uses_compact_metrics_grid_steps_and_stacked_workbench(self):
        index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        auto_labeling_css = (ROOT / "static" / "styles" / "pages" / "auto_labeling.css").read_text(encoding="utf-8")

        self.assertIn("/static/style.css?v=20260709-export-layout", index_html)
        self.assertIn('data-i18n="autoLabel.executionConsole"', index_html)
        self.assertIn('data-i18n="autoLabel.executionConsoleHelp"', index_html)
        self.assertIn('data-i18n="autoLabel.reviewWorkspaceHelp"', index_html)
        self.assertIn('data-i18n="autoLabel.jobHistoryHelp"', index_html)
        self.assertIn(".auto-label-status-strip .metric-card", auto_labeling_css)
        self.assertIn("min-height: 58px", auto_labeling_css)
        self.assertIn(".auto-label-safety-rail li", auto_labeling_css)
        self.assertIn(".auto-label-workbench", auto_labeling_css)
        self.assertIn("grid-template-columns: minmax(0, 1fr);", auto_labeling_css)
        self.assertIn(".auto-job-builder", auto_labeling_css)
        self.assertIn(".auto-execution-console-panel", auto_labeling_css)
        self.assertIn(".auto-review-first-panel", auto_labeling_css)
        self.assertIn(".auto-setup-summary-panel", auto_labeling_css)
        self.assertIn("grid-template-columns: minmax(260px, 0.9fr) minmax(340px, 1.25fr) minmax(300px, 1fr);", auto_labeling_css)
        self.assertIn(".output-target-block", auto_labeling_css)
        self.assertIn("grid-template-columns: minmax(170px, 0.34fr) minmax(0, 1fr) auto;", auto_labeling_css)
        self.assertIn(".review-preview-grid", auto_labeling_css)
        self.assertIn(".result-overlay-tile", auto_labeling_css)
        self.assertIn(".original-reference-tile", auto_labeling_css)
        self.assertIn(".review-nav-button", auto_labeling_css)
        self.assertIn(".auto-review-workstation", auto_labeling_css)
        self.assertIn(".auto-review-workspace-panel", auto_labeling_css)
        self.assertIn(".auto-shape-review-grid", auto_labeling_css)
        self.assertIn(".auto-review-action-card", auto_labeling_css)
        self.assertIn("@media (max-width: 1600px)", auto_labeling_css)
        self.assertIn("@media (max-width: 1180px)", auto_labeling_css)
        self.assertIn("@media (max-width: 840px)", auto_labeling_css)
        self.assertIn("grid-column: 1 / -1", auto_labeling_css)
        self.assertIn(".review-preview-grid .preview-tile > div", auto_labeling_css)
        self.assertIn("min-height: 560px", auto_labeling_css)
        self.assertIn("min-height: 260px", auto_labeling_css)
        self.assertIn("#auto-review-overlay img", auto_labeling_css)
        self.assertIn("width: auto;", auto_labeling_css)
        self.assertIn("max-height: 100%;", auto_labeling_css)
        self.assertIn("border: 0;", auto_labeling_css)

    def test_draft_rules_are_editable_and_sent_to_job_request(self):
        index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        auto_labeling_js = (ROOT / "static" / "pages" / "auto_labeling.js").read_text(encoding="utf-8")

        for element_id in [
            "auto-confidence",
            "auto-iou",
            "auto-max-detections",
            "auto-min-mask-area",
            "auto-output-mode",
            "auto-class-filter",
        ]:
            self.assertIn(f'id="{element_id}"', index_html)

        self.assertIn("function readAutoDraftRules()", auto_labeling_js)
        self.assertIn("conf:", auto_labeling_js)
        self.assertIn("iou:", auto_labeling_js)
        self.assertIn("max_det:", auto_labeling_js)
        self.assertIn("min_mask_area:", auto_labeling_js)
        self.assertIn("output_mode:", auto_labeling_js)
        self.assertIn("...draftRules", auto_labeling_js)

    def test_draft_job_button_is_connected_to_auto_labeling_api(self):
        index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        auto_labeling_js = (ROOT / "static" / "pages" / "auto_labeling.js").read_text(encoding="utf-8")

        self.assertIn('id="btn-start-auto-label"', index_html)
        self.assertIn("createAutoLabelJob", auto_labeling_js)
        self.assertIn("/auto-labeling/jobs", auto_labeling_js)
        self.assertIn("renderAutoLabelJobHistory", auto_labeling_js)

    def test_review_queue_can_open_labelme_json_and_preview_overlay(self):
        index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        auto_labeling_js = (ROOT / "static" / "pages" / "auto_labeling.js").read_text(encoding="utf-8")

        self.assertIn('id="auto-review-queue-body"', index_html)
        self.assertIn('id="auto-review-original"', index_html)
        self.assertIn('id="auto-review-overlay"', index_html)
        self.assertIn('id="btn-auto-review-prev"', index_html)
        self.assertIn('id="btn-auto-review-next"', index_html)
        self.assertIn('id="auto-review-position"', index_html)
        self.assertNotIn('id="auto-review-original" data-i18n=', index_html)
        self.assertNotIn('id="auto-review-overlay" data-i18n=', index_html)
        self.assertIn("renderAutoLabelReviewQueue", auto_labeling_js)
        self.assertIn("getAutoLabelReviewItems", auto_labeling_js)
        self.assertIn("data-auto-review-preview", auto_labeling_js)
        self.assertIn("draft_labelme_url", auto_labeling_js)
        self.assertIn("preview_url", auto_labeling_js)
        self.assertIn('id="auto-shape-table-body"', index_html)
        self.assertIn('id="auto-review-job-id"', index_html)
        self.assertIn("renderAutoShapeTable", auto_labeling_js)
        self.assertIn("renderAutoReviewTaskInfo", auto_labeling_js)

    def test_review_toolbar_is_connected_to_review_actions(self):
        index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        auto_labeling_js = (ROOT / "static" / "pages" / "auto_labeling.js").read_text(encoding="utf-8")

        for element_id in [
            "btn-auto-review-accept",
            "btn-auto-review-reject",
            "btn-auto-review-accept-next",
            "btn-auto-review-reject-next",
            "btn-auto-review-skip",
            "btn-auto-review-edit",
            "btn-auto-review-hard-case",
        ]:
            self.assertIn(f'id="{element_id}"', index_html)

        self.assertIn('reviewSelectedAutoLabelItem("accept")', auto_labeling_js)
        self.assertIn('reviewSelectedAutoLabelItem("reject")', auto_labeling_js)
        self.assertIn('reviewSelectedAutoLabelItem("accept", { moveNext: true })', auto_labeling_js)
        self.assertIn('reviewSelectedAutoLabelItem("reject", { moveNext: true })', auto_labeling_js)
        self.assertIn("navigateAutoReviewItem", auto_labeling_js)
        self.assertIn('reviewSelectedAutoLabelItem("skip")', auto_labeling_js)
        self.assertIn('reviewSelectedAutoLabelItem("hard_case")', auto_labeling_js)
        self.assertIn("editSelectedAutoLabelItem", auto_labeling_js)
        self.assertIn("/review", auto_labeling_js)
        self.assertIn("openAutoLabelReviewUrl", auto_labeling_js)
        self.assertIn("new URL(url, window.location.origin).toString()", auto_labeling_js)
        self.assertIn("const hasDraftJson = Boolean(selectedAutoReviewItem?.draft_labelme_url)", auto_labeling_js)
        self.assertIn('editButton.disabled = !hasDraftJson', auto_labeling_js)
        self.assertIn('t("autoLabel.editDraftTitle")', auto_labeling_js)
        self.assertIn('t("autoLabel.selectDraftJsonTitle")', auto_labeling_js)


if __name__ == "__main__":
    unittest.main()
