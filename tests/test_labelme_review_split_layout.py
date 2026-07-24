import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LabelMeReviewAndSplitLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        cls.labelme_js = (ROOT / "static" / "pages" / "labelme.js").read_text(encoding="utf-8")
        cls.split_js = (ROOT / "static" / "pages" / "split.js").read_text(encoding="utf-8")
        cls.split_css = (ROOT / "static" / "styles" / "pages" / "split.css").read_text(encoding="utf-8")
        cls.zh_tw = (ROOT / "static" / "state" / "i18n" / "zh-TW.js").read_text(encoding="utf-8")
        cls.en = (ROOT / "static" / "state" / "i18n" / "en.js").read_text(encoding="utf-8")

    def test_labelme_review_queue_exposes_safe_bulk_cleanup(self):
        self.assertIn('id="btn-clear-selected-review"', self.html)
        self.assertIn('id="chk-select-all-review"', self.html)
        self.assertIn("data-clear-import-file", self.labelme_js)
        self.assertIn("/failed-sources/clear", self.labelme_js)
        self.assertIn("selectedImportReviewFiles", self.labelme_js)

    def test_split_uses_two_by_two_workspace_with_spanning_distribution_panel(self):
        self.assertIn('class="panel-section split-config-panel"', self.html)
        self.assertIn('class="panel-section split-preview-panel"', self.html)
        self.assertIn('class="panel-section split-class-panel"', self.html)
        self.assertIn("grid-row: 1 / span 2", self.split_css)
        self.assertIn('id="split-set-counts"', self.html)
        self.assertIn('id="split-class-distribution"', self.html)

    def test_split_distribution_supports_actual_and_estimated_counts(self):
        self.assertIn("report?.class_distribution", self.split_js)
        self.assertIn("report?.split_counts", self.split_js)
        self.assertIn("estimateClassDistribution", self.split_js)
        self.assertIn("allocateIntegerCounts", self.split_js)
        self.assertIn("split.distribution.actual", self.split_js)
        self.assertIn("split.distribution.estimated", self.split_js)

    def test_new_review_and_distribution_text_is_bilingual(self):
        keys = [
            "labelme.reviewQueueHelp",
            "labelme.clearSelected",
            "labelme.review.clearConfirm",
            "labelme.review.cleared",
            "split.classDistributionTitle",
            "split.classDistributionHelp",
            "split.distribution.actual",
            "split.distribution.estimated",
        ]
        for key in keys:
            with self.subTest(key=key):
                self.assertIn(f'"{key}"', self.zh_tw)
                self.assertIn(f'"{key}"', self.en)


if __name__ == "__main__":
    unittest.main()
