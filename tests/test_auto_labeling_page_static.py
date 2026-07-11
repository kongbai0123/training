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
        auto_labeling_js = (ROOT / "static" / "pages" / "auto_labeling.js").read_text(encoding="utf-8")

        self.assertIn("/static/style.css?v=20260711-layout-export-precision", index_html)
        self.assertIn('data-i18n="autoLabel.executionConsole"', index_html)
        self.assertIn('data-i18n="autoLabel.executionConsoleHelp"', index_html)
        self.assertIn('data-i18n="autoLabel.reviewWorkspaceHelp"', index_html)
        self.assertIn('data-i18n="autoLabel.jobHistoryHelp"', index_html)
        self.assertIn(".auto-label-status-strip .metric-card", auto_labeling_css)
        self.assertIn("min-height: 58px", auto_labeling_css)
        self.assertIn(".auto-label-page-guide-track", auto_labeling_css)
        self.assertIn('data-i18n="autoLabel.flowTitle"', index_html)
        self.assertIn('data-auto-scroll-target="#auto-label-execution-section"', index_html)
        self.assertIn('data-auto-scroll-target="#btn-start-auto-label"', index_html)
        self.assertIn('data-auto-scroll-target="#auto-label-review-section"', index_html)
        self.assertIn('id="auto-label-execution-section" tabindex="-1"', index_html)
        self.assertIn('id="auto-label-review-section" tabindex="-1"', index_html)
        self.assertIn("function initAutoLabelPageGuide()", auto_labeling_js)
        self.assertIn('target.scrollIntoView({ behavior: "smooth", block: "start" })', auto_labeling_js)
        self.assertNotIn(".auto-label-flow-engine", auto_labeling_css)
        self.assertIn(".auto-label-workbench", auto_labeling_css)
        self.assertIn("grid-template-columns: minmax(0, 1fr);", auto_labeling_css)
        self.assertIn(".auto-job-builder", auto_labeling_css)
        self.assertIn(".auto-execution-console-panel", auto_labeling_css)
        self.assertIn(".auto-review-first-panel", auto_labeling_css)
        self.assertIn(".auto-setup-summary-panel", auto_labeling_css)
        self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr));", auto_labeling_css)
        self.assertIn(".auto-source-drop-card", auto_labeling_css)
        self.assertIn(".auto-source-choice-row", auto_labeling_css)
        self.assertIn(".auto-step-heading .auto-step-number", auto_labeling_css)
        self.assertNotIn(".auto-step-heading span {", auto_labeling_css)
        self.assertIn(".auto-model-source-grid", auto_labeling_css)
        self.assertIn(".model-select-shell select", auto_labeling_css)
        self.assertIn(".auto-rule-settings-grid .auto-class-filter-field", auto_labeling_css)
        self.assertIn(".auto-label-start-action", auto_labeling_css)
        self.assertNotIn('class="output-target-block"', index_html)
        self.assertIn('id="auto-start-reason" aria-live="polite"', index_html)
        self.assertIn(".auto-rules-step-block", auto_labeling_css)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", auto_labeling_css)
        self.assertIn(".auto-rule-settings-grid .auto-output-mode-field", auto_labeling_css)
        self.assertIn(".auto-review-policy-summary", auto_labeling_css)
        self.assertIn('data-i18n="autoLabel.reviewPolicySummary"', index_html)
        self.assertIn('data-i18n-tooltip="autoLabel.reviewPolicyTooltip"', index_html)
        self.assertNotIn('class="advanced-collapse auto-review-priority-collapse"', index_html)
        self.assertIn(".review-preview-grid", auto_labeling_css)
        self.assertIn(".result-overlay-tile", auto_labeling_css)
        self.assertIn(".original-reference-tile", auto_labeling_css)
        self.assertIn(".review-nav-button", auto_labeling_css)
        self.assertIn(".auto-review-workstation", auto_labeling_css)
        self.assertIn(".auto-review-side-column", auto_labeling_css)
        self.assertIn(".auto-review-workspace-panel", auto_labeling_css)
        self.assertIn(".auto-shape-review-grid", auto_labeling_css)
        self.assertIn(".auto-shape-review-grid .draft-inspector", auto_labeling_css)
        self.assertIn("grid-template-columns: repeat(4, minmax(0, 1fr));", auto_labeling_css)
        self.assertIn(".auto-review-action-card", auto_labeling_css)
        self.assertIn("@media (max-width: 1600px)", auto_labeling_css)
        self.assertIn("@media (max-width: 1180px)", auto_labeling_css)
        self.assertIn("@media (max-width: 840px)", auto_labeling_css)
        self.assertIn("grid-column: 1 / -1", auto_labeling_css)
        self.assertIn(".review-preview-grid .preview-tile > div", auto_labeling_css)
        self.assertIn("min-height: 620px", auto_labeling_css)
        self.assertIn("min-height: 150px", auto_labeling_css)
        self.assertIn("position: absolute", auto_labeling_css)
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

        self.assertIn("auto-rule-settings-grid", index_html)
        self.assertLess(index_html.index('id="auto-output-mode"'), index_html.index('id="auto-class-filter"'))
        self.assertIn('class="auto-class-filter-field"', index_html)
        self.assertIn('id="btn-add-auto-class-filter"', index_html)
        self.assertIn('id="auto-class-filter-chips"', index_html)

        self.assertIn("function readAutoDraftRules()", auto_labeling_js)
        self.assertIn("function initAutoClassFilter()", auto_labeling_js)
        self.assertIn("function commitAutoClassFilterInput()", auto_labeling_js)
        self.assertIn("function renderAutoClassFilterChips()", auto_labeling_js)
        self.assertIn('event.key !== "Enter"', auto_labeling_js)
        self.assertIn("autoClassFilterValues", auto_labeling_js)
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
        for button_id in [
            "btn-refresh-auto-label-models",
            "btn-open-weight-manager",
            "btn-start-auto-label",
        ]:
            id_index = index_html.index(f'id="{button_id}"')
            tag_start = index_html.rfind("<button", 0, id_index)
            tag_end = index_html.index(">", id_index)
            button_tag = index_html[tag_start:tag_end]
            self.assertNotIn(" disabled", button_tag)
            self.assertNotIn(" guarded", button_tag)
        self.assertIn("createAutoLabelJob", auto_labeling_js)
        self.assertIn("refreshAutoLabelModelsFromAction", auto_labeling_js)
        self.assertIn("autoLabelStartReasonKey", auto_labeling_js)
        self.assertIn("action-requires-attention", auto_labeling_js)
        self.assertIn("function showAutoLabelWarning(messageKey)", auto_labeling_js)
        self.assertIn('severity: "warning"', auto_labeling_js)
        self.assertIn('showAutoLabelWarning("autoLabel.startReason.busy")', auto_labeling_js)
        self.assertIn("/auto-labeling/jobs", auto_labeling_js)
        self.assertIn("renderAutoLabelJobHistory", auto_labeling_js)

    def test_task_setup_uses_source_drop_card_model_select_and_external_drop(self):
        index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        auto_labeling_js = (ROOT / "static" / "pages" / "auto_labeling.js").read_text(encoding="utf-8")
        en = (ROOT / "static" / "state" / "i18n" / "en.js").read_text(encoding="utf-8")
        zh = (ROOT / "static" / "state" / "i18n" / "zh-TW.js").read_text(encoding="utf-8")

        self.assertIn('class="drop-zone auto-source-drop-card"', index_html)
        self.assertIn('data-i18n-tooltip="autoLabel.inputTooltip"', index_html)
        self.assertNotIn('data-i18n="autoLabel.source.unlabeledHelp"', index_html)
        self.assertNotIn('data-i18n="autoLabel.source.invalidHelp"', index_html)
        self.assertNotIn('data-model-source=', index_html)
        self.assertIn('class="auto-model-source-grid"', index_html)
        self.assertIn('id="auto-label-model-list" class="model-select-shell"', index_html)
        self.assertIn('class="drop-zone model-drop-zone"', index_html)
        self.assertIn('id="auto-label-model-select"', auto_labeling_js)
        self.assertIn("model-select-meta", auto_labeling_js)
        self.assertIn('"autoLabel.inputTooltip"', en)
        self.assertIn('"autoLabel.inputTooltip"', zh)

    def test_review_queue_can_open_labelme_json_and_preview_overlay(self):
        index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        auto_labeling_js = (ROOT / "static" / "pages" / "auto_labeling.js").read_text(encoding="utf-8")

        self.assertIn('id="auto-review-queue-body"', index_html)
        self.assertIn('id="auto-review-original"', index_html)
        self.assertIn('id="auto-review-overlay"', index_html)
        self.assertIn('id="btn-auto-review-prev"', index_html)
        self.assertIn('id="btn-auto-review-next"', index_html)
        self.assertIn('id="auto-review-position"', index_html)
        self.assertNotIn('data-i18n="autoLabel.fit"', index_html)
        self.assertNotIn(">100%</button>", index_html)
        self.assertNotIn('id="auto-review-original" data-i18n=', index_html)
        self.assertNotIn('id="auto-review-overlay" data-i18n=', index_html)
        self.assertIn("renderAutoLabelReviewQueue", auto_labeling_js)
        self.assertIn("getAutoLabelReviewItems", auto_labeling_js)
        self.assertIn("data-auto-review-preview", auto_labeling_js)
        self.assertIn("draft_labelme_url", auto_labeling_js)
        self.assertIn("preview_url", auto_labeling_js)
        self.assertNotIn('id="auto-shape-table-body"', index_html)
        self.assertIn('id="auto-review-job-id"', index_html)
        self.assertNotIn("renderAutoShapeTable", auto_labeling_js)
        self.assertIn("renderAutoReviewTaskInfo", auto_labeling_js)

    def test_review_toolbar_is_connected_to_review_actions(self):
        index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        auto_labeling_js = (ROOT / "static" / "pages" / "auto_labeling.js").read_text(encoding="utf-8")

        for element_id in [
            "btn-auto-review-accept-next",
            "btn-auto-review-reject-next",
            "btn-auto-review-skip",
            "btn-auto-review-edit",
            "btn-auto-review-hard-case",
        ]:
            self.assertIn(f'id="{element_id}"', index_html)

        self.assertIn('reviewSelectedAutoLabelItem("accept", { moveNext: true })', auto_labeling_js)
        self.assertIn('reviewSelectedAutoLabelItem("reject", { moveNext: true })', auto_labeling_js)
        self.assertNotIn('id="btn-auto-review-accept"', index_html)
        self.assertNotIn('id="btn-auto-review-reject"', index_html)
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
