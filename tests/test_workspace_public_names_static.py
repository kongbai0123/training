import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkspacePublicNamesStaticTests(unittest.TestCase):
    def test_public_entry_points_use_data_first_names(self):
        index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        zh = (ROOT / "static" / "state" / "i18n" / "zh-TW.js").read_text(encoding="utf-8")
        en = (ROOT / "static" / "state" / "i18n" / "en.js").read_text(encoding="utf-8")

        for key in ("workspace.kind.image", "workspace.kind.sequence", "workspace.kind.tabular"):
            self.assertIn(f'data-i18n="{key}"', index)
            self.assertIn(f'"{key}"', zh)
            self.assertIn(f'"{key}"', en)

        self.assertIn('"dashboard.module.cnn.title": "影像訓練"', zh)
        self.assertIn('"dashboard.module.rnn.title": "序列訓練"', zh)
        self.assertIn('"dashboard.module.tabular.title": "表格資料預測"', zh)
        self.assertIn('"dashboard.module.cnn.title": "Image Training"', en)
        self.assertIn('"dashboard.module.rnn.title": "Sequence Training"', en)
        self.assertIn('"dashboard.module.tabular.title": "Tabular Data Prediction"', en)
        self.assertIn("不使用前後列時間順序", zh)
        self.assertIn("XGBoost", zh)

    def test_machine_identifiers_remain_stable(self):
        index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        for value in (
            "object_detection",
            "image_classification",
            "sequence_classification",
            "sequence_regression",
            "tabular_classification",
            "tabular_regression",
        ):
            self.assertIn(f'value="{value}"', index)


if __name__ == "__main__":
    unittest.main()
