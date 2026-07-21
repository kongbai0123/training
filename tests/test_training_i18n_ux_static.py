import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TrainingI18nUxStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        cls.training_js = (ROOT / "static" / "pages" / "training.js").read_text(encoding="utf-8")
        cls.trainer_py = (ROOT / "src" / "trainer.py").read_text(encoding="utf-8")
        cls.augmentation_js = (ROOT / "static" / "pages" / "augmentation.js").read_text(encoding="utf-8")
        cls.inference_js = (ROOT / "static" / "pages" / "inference.js").read_text(encoding="utf-8")
        cls.projects_js = (ROOT / "static" / "pages" / "projects.js").read_text(encoding="utf-8")
        cls.rnn_guide_js = (ROOT / "static" / "pages" / "rnn_model_render_helpers.js").read_text(encoding="utf-8")
        cls.training_css = (ROOT / "static" / "styles" / "pages" / "training.css").read_text(encoding="utf-8")
        cls.zh_catalog = (ROOT / "static" / "state" / "i18n" / "zh-TW.js").read_text(encoding="utf-8")
        cls.en_catalog = (ROOT / "static" / "state" / "i18n" / "en.js").read_text(encoding="utf-8")
        cls.model_setup_js = (ROOT / "static" / "core" / "model_setup.js").read_text(encoding="utf-8")
        cls.tooltip_js = (ROOT / "static" / "core" / "tooltip.js").read_text(encoding="utf-8")
        cls.i18n_audit_js = (ROOT / "scripts" / "i18n_dom_audit.mjs").read_text(encoding="utf-8")

    def test_training_fields_remain_unique_after_layout_grouping(self):
        field_ids = (
            "train-run-id-input",
            "train-profile",
            "train-model",
            "train-epochs",
            "train-batch",
            "train-imgsz",
            "train-device",
            "train-lr-mode",
            "train-lr0",
            "train-optimizer",
            "train-early-stop-enabled",
            "train-patience",
            "train-workers-mode",
            "train-workers",
            "train-seed",
            "train-save-period",
            "train-close-mosaic",
            "train-amp",
            "train-cache",
        )
        for field_id in field_ids:
            with self.subTest(field_id=field_id):
                self.assertEqual(len(re.findall(fr'id=["\']{re.escape(field_id)}["\']', self.index_html)), 1)

    def test_training_configuration_uses_semantic_groups_without_mode_tabs(self):
        self.assertNotIn('id="tab-config-simple"', self.index_html)
        self.assertNotIn('id="tab-config-advanced"', self.index_html)
        self.assertIn('data-i18n="training.group.resources"', self.index_html)
        self.assertIn('class="training-model-controls"', self.index_html)
        self.assertIn('class="training-advanced-column" id="config-advanced-fields"', self.index_html)
        self.assertIn('class="training-model-details"', self.index_html)
        self.assertNotIn('qs("#tab-config-simple")', self.training_js)
        self.assertNotIn('qs("#tab-config-advanced")', self.training_js)

    def test_screenshot_tooltips_have_traditional_chinese_catalog_values(self):
        expected = {
            "split.methodTooltip": "分層分割會盡可能維持類別比例",
            "training.epochsTooltip": "完整看過一次訓練資料",
            "training.batchTooltip": "顯示記憶體",
            "training.deviceTooltip": "選擇執行訓練的硬體",
            "training.lrTooltip": "控制每次更新模型的幅度",
            "training.optimizerTooltip": "負責更新模型權重",
            "training.workersTooltip": "在背景準備訓練資料",
            "training.savePeriodTooltip": "checkpoint",
            "training.closeMosaicTooltip": "控制訓練後期的資料擴充",
        }
        for key, value in expected.items():
            with self.subTest(key=key):
                self.assertRegex(self.zh_catalog, rf'"{re.escape(key)}"\s*:\s*"[^"]*{re.escape(value)}')

    def test_dynamic_augmentation_labels_use_i18n(self):
        self.assertIn('t("augmentation.job.generated")', self.augmentation_js)
        self.assertIn('t("augmentation.job.trainSource")', self.augmentation_js)
        self.assertIn('t("augmentation.job.multiplier")', self.augmentation_js)
        self.assertNotIn('<small>generated</small>', self.augmentation_js)

    def test_training_report_has_no_remote_image_fallback(self):
        self.assertNotIn("raw.githubusercontent.com", self.training_js)
        self.assertIn('t("training.reportImageUnavailable")', self.training_js)

    def test_training_profiles_use_hidden_contextual_explanations(self):
        self.assertNotIn('id="training-profile-guide"', self.index_html)
        self.assertIn('id="training-profile-info"', self.index_html)
        self.assertNotIn("const TRAINING_PROFILES", self.training_js)
        self.assertNotIn("function applyTrainingProfile(profile)", self.training_js)
        self.assertNotIn("applyTrainingProfile(event.target.value)", self.training_js)
        self.assertIn("function syncTrainingProfileTooltip()", self.training_js)
        self.assertNotIn('"#train-epochs": preset.epochs', self.training_js)
        self.assertNotIn('t("training.profileParameters")', self.training_js)
        self.assertNotIn(".training-profile-guide {", self.training_css)
        for profile in ("Balanced", "Quick", "Accuracy", "Custom"):
            self.assertIn(f'"training.profile{profile}Use"', self.training_js)
            self.assertIn(f'"training.profile{profile}Benefit"', self.training_js)
            self.assertIn(f'"training.profile{profile}Caution"', self.training_js)
        self.assertIn('"training.profileQuickCaution"', self.zh_catalog)
        self.assertIn('"training.profileAccuracyBenefit"', self.zh_catalog)

    def test_shell_and_model_task_filters_have_bidirectional_i18n_keys(self):
        shell_keys = (
            "overview", "history", "settings", "dataset", "split", "augmentation",
            "training", "evaluation", "inference", "compare", "autoLabel", "export",
            "sequenceDataset", "featuresLabels", "windowing", "sequenceTest",
        )
        for key in shell_keys:
            with self.subTest(key=key):
                token = f'shell.nav.{key}'
                self.assertIn(f'data-i18n="{token}"', self.index_html)
                self.assertIn(f'"{token}"', self.en_catalog)
                self.assertIn(f'"{token}"', self.zh_catalog)

        for key in ("imageClassification", "objectDetection", "instanceSegmentation", "semanticSegmentation"):
            with self.subTest(key=key):
                token = f'modelSetup.task.{key}'
                self.assertIn(f'data-i18n="{token}"', self.index_html)
                self.assertIn(f't("{token}")', self.model_setup_js)
                self.assertIn(f'"{token}"', self.en_catalog)
                self.assertIn(f'"{token}"', self.zh_catalog)

    def test_model_selector_parameters_advanced_and_specification_use_three_columns(self):
        self.assertIn('class="training-model-workbench"', self.index_html)
        self.assertNotIn('class="model-registry-header"', self.index_html)
        self.assertIn('class="training-model-selector"', self.index_html)
        self.assertIn('class="training-parameter-card"', self.index_html)
        self.assertIn('class="training-advanced-column"', self.index_html)
        self.assertIn('class="training-model-details"', self.index_html)
        self.assertIn('data-i18n="training.modelSelectionTitle"', self.index_html)
        self.assertIn('data-i18n="training.modelDetailsTitle"', self.index_html)
        self.assertIn('id="training-model-description"', self.index_html)
        self.assertIn('class="training-model-spec-list"', self.index_html)
        self.assertIn('class="training-secondary-advanced-grid"', self.index_html)
        self.assertRegex(
            self.training_css,
            r"\.training-model-workbench\s*\{[^}]*grid-template-columns:\s*minmax\(290px,\s*1fr\)\s+minmax\(310px,\s*1fr\)\s+minmax\(360px,\s*1\.08fr\)",
        )
        for token in (
            "training.modelSelectionTitle",
            "training.modelSelectionHelp",
            "training.modelDetailsTitle",
            "training.modelDetailsHelp",
        ):
            with self.subTest(token=token):
                self.assertIn(f'"{token}"', self.en_catalog)
                self.assertIn(f'"{token}"', self.zh_catalog)
        self.assertNotRegex(
            self.training_css,
            r"@media \(max-width: 980px\)[\s\S]*?\.training-model-workbench\s*\{\s*grid-template-columns:\s*1fr;",
        )

    def test_cnn_and_rnn_learning_rate_fields_offer_auto_and_custom_modes(self):
        self.assertIn('id="train-lr-mode"', self.index_html)
        self.assertIn('id="train-workers-mode"', self.index_html)
        self.assertIn('id="rnn-lr-mode"', self.index_html)
        self.assertEqual(self.index_html.count('data-i18n="training.valueMode.auto"'), 3)
        self.assertEqual(self.index_html.count('data-i18n="training.valueMode.custom"'), 3)
        self.assertIn("AUTO_PARAMETER_FIELDS", self.training_js)
        self.assertIn('lr0_mode: qs("#train-lr-mode")?.value || "auto"', self.training_js)
        self.assertIn('workers_mode: qs("#train-workers-mode")?.value || "auto"', self.training_js)
        self.assertIn("setAutomaticParameterValue(\"#train-lr0\", data.lr0)", self.training_js)
        self.assertIn("setAutomaticParameterValue(\"#train-workers\", data.workers)", self.training_js)
        self.assertIn('workers_mode != "custom"', self.trainer_py)

    def test_early_stop_is_explicitly_enabled_and_model_is_not_marked_recommended(self):
        self.assertIn('id="train-early-stop-enabled"', self.index_html)
        self.assertIn('data-i18n="training.earlyStopRounds"', self.index_html)
        self.assertIn('? Number(qs("#train-patience")?.value || 20)', self.training_js)
        self.assertIn("stripModelRecommendationLabel", self.training_js)
        self.assertNotIn("YOLOv8n Segmentation (Recommended)", self.index_html)
        self.assertNotIn("YOLOv8n 分割（建議）", self.zh_catalog)

    def test_training_tooltips_use_title_and_bulleted_items(self):
        self.assertIn(".split(/[;；]/)", self.tooltip_js)
        self.assertIn('attributeFilter: ["data-tooltip"]', self.tooltip_js)
        self.assertIn('icon.setAttribute("aria-label", icon.dataset.tooltip)', self.tooltip_js)
        for token in (
            "training.modelTooltip",
            "training.epochsTooltip",
            "training.batchTooltip",
            "training.imgszTooltip",
            "training.deviceTooltip",
            "training.lrTooltip",
            "training.optimizerTooltip",
            "training.earlyStopTooltip",
            "training.workersTooltip",
            "training.seedTooltip",
            "training.savePeriodTooltip",
            "training.closeMosaicTooltip",
            "training.ampTooltip",
            "training.cacheTooltip",
        ):
            with self.subTest(token=token):
                for catalog in (self.en_catalog, self.zh_catalog):
                    match = re.search(rf'"{re.escape(token)}"\s*:\s*"([^"]+)"', catalog)
                    self.assertIsNotNone(match)
                    separator_count = match.group(1).count(";") + match.group(1).count("；")
                    self.assertGreaterEqual(separator_count, 2)

    def test_i18n_browser_audit_checks_both_language_directions(self):
        self.assertIn("cjk_in_non_zh_mode", self.i18n_audit_js)
        self.assertIn("english_in_zh_mode", self.i18n_audit_js)
        self.assertIn("if (!isVisible(element)) return;", self.i18n_audit_js)
        self.assertIn("viewport: { width: 1920, height: 1080 }", self.i18n_audit_js)
        self.assertIn('target.page.endsWith("-modal")', self.i18n_audit_js)

    def test_dynamic_empty_states_and_rnn_guide_use_translation_keys(self):
        self.assertIn('t("augmentation.message.noProject")', self.augmentation_js)
        self.assertIn('t("augmentation.job.empty")', self.augmentation_js)
        self.assertIn('t("inference.empty.loadProject")', self.inference_js)
        self.assertIn('t("inference.empty.noResult")', self.inference_js)
        self.assertIn('t("rnn.guide.bestFor")', self.rnn_guide_js)
        self.assertIn('t("rnn.guide.risk")', self.rnn_guide_js)

    def test_hidden_workflow_dialogs_have_explicit_translation_keys(self):
        for token in (
            "project.createTitle",
            "project.deleteTitle",
            "inference.detailTitle",
            "modelImport.title",
            "modelImport.safety",
            "weightManager.title",
            "weightManager.testRunTitle",
        ):
            with self.subTest(token=token):
                self.assertIn(f'data-i18n="{token}"', self.index_html)
                self.assertIn(f'"{token}"', self.en_catalog)
                self.assertIn(f'"{token}"', self.zh_catalog)

    def test_project_task_selector_uses_plain_language_in_both_languages(self):
        task_keys = (
            "project.task.objectDetection",
            "project.task.imageClassification",
            "project.task.instanceSegmentation",
            "project.task.semanticSegmentation",
            "project.task.sequenceClassification",
            "project.task.sequenceRegression",
        )
        for token in task_keys:
            with self.subTest(token=token):
                self.assertIn(f'data-i18n="{token}"', self.index_html)
                self.assertIn(f'"{token}"', self.zh_catalog)
                self.assertIn(f'"{token}"', self.en_catalog)
        self.assertIn('id="new-project-task-hint"', self.index_html)
        self.assertIn('t(`project.taskHelp.${type}`)', self.projects_js)
        self.assertNotIn('<option value="image_classification">Image Classification</option>', self.index_html)

    def test_project_task_selector_has_quick_guide_tooltip_and_edit_flow(self):
        self.assertGreaterEqual(self.index_html.count('data-i18n-tooltip="project.taskTypeTooltip"'), 2)
        self.assertIn('id="new-project-task-quick-guide"', self.index_html)
        self.assertIn('id="project-task-edit-modal"', self.index_html)
        self.assertIn('id="project-task-edit-quick-guide"', self.index_html)
        self.assertIn('data-edit-project-task=', self.projects_js)
        self.assertIn('data-project-task-choice=', self.projects_js)
        self.assertIn('method: "PATCH"', self.projects_js)
        self.assertIn('JSON.stringify({ task_type: taskType, confirm: true })', self.projects_js)
        for task_type in (
            "object_detection",
            "image_classification",
            "instance_segmentation",
            "semantic_segmentation",
            "sequence_classification",
            "sequence_regression",
        ):
            with self.subTest(task_type=task_type):
                for prefix in ("project.taskShort", "project.taskCard"):
                    token = f'{prefix}.{task_type}'
                    self.assertIn(f'"{token}"', self.zh_catalog)
                    self.assertIn(f'"{token}"', self.en_catalog)
        for token in (
            "project.taskTypeTooltip",
            "project.taskEditTitle",
            "project.taskEditImpact",
            "project.taskEditButton",
            "project.taskEditSuccess",
        ):
            with self.subTest(token=token):
                self.assertIn(f'"{token}"', self.zh_catalog)
                self.assertIn(f'"{token}"', self.en_catalog)

    def test_installed_models_are_uncluttered_and_saved_run_model_wins_over_recommendation(self):
        self.assertNotIn('if (item.installed) statusNotes.push(t("modelSetup.installed"))', self.training_js)
        self.assertIn('if (!item.installed && item.installation_required)', self.training_js)
        self.assertIn('const savedRunModel = appState.currentProject?.training_config?.run_id', self.training_js)
        self.assertIn('const preferred = [savedRunModel, previous].find(', self.training_js)
        self.assertIn('const hasSavedRunConfig = Boolean(savedConfig.run_id);', self.training_js)
        self.assertIn('const data = hasSavedRunConfig ? { ...recommendation, ...savedConfig } : recommendation;', self.training_js)
        self.assertIn('Array.from(modelSelect.options).some((option) => option.value === data.model)', self.training_js)


if __name__ == "__main__":
    unittest.main()
