import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TrainingI18nUxStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        cls.training_js = (ROOT / "static" / "pages" / "training.js").read_text(encoding="utf-8")
        cls.augmentation_js = (ROOT / "static" / "pages" / "augmentation.js").read_text(encoding="utf-8")
        cls.training_css = (ROOT / "static" / "styles" / "pages" / "training.css").read_text(encoding="utf-8")
        cls.zh_catalog = (ROOT / "static" / "state" / "i18n" / "zh-TW.js").read_text(encoding="utf-8")

    def test_training_fields_remain_unique_after_layout_grouping(self):
        field_ids = (
            "train-run-id-input",
            "train-profile",
            "train-model",
            "train-epochs",
            "train-batch",
            "train-imgsz",
            "train-device",
            "train-lr0",
            "train-optimizer",
            "train-patience",
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

    def test_training_configuration_uses_semantic_groups_and_segmented_mode(self):
        self.assertIn('class="config-mode-button active" id="tab-config-simple"', self.index_html)
        self.assertIn('class="config-mode-button" id="tab-config-advanced"', self.index_html)
        self.assertIn('data-i18n="training.group.resources"', self.index_html)
        self.assertIn('data-i18n="training.group.optimization"', self.index_html)
        self.assertIn('data-i18n="training.group.runtime"', self.index_html)
        self.assertIn('data-i18n="training.group.precision"', self.index_html)
        self.assertIn('.training-field-grid-4 {', self.training_css)
        self.assertIn('classList.add("active")', self.training_js)
        self.assertNotIn('classList.contains("btn-primary")', self.training_js)

    def test_screenshot_tooltips_have_traditional_chinese_catalog_values(self):
        expected = {
            "split.methodTooltip": "分層分割會盡可能維持類別比例",
            "training.epochsTooltip": "完整看過一次訓練資料",
            "training.batchTooltip": "顯示記憶體",
            "training.deviceTooltip": "有 CUDA 時建議使用 GPU",
            "training.lrTooltip": "初始學習率",
            "training.optimizerTooltip": "最佳化器",
            "training.workersTooltip": "平行載入資料",
            "training.savePeriodTooltip": "checkpoint",
            "training.closeMosaicTooltip": "訓練後期停用 Mosaic",
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


if __name__ == "__main__":
    unittest.main()
