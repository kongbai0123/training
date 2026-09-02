import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkspaceInformationArchitectureStaticTests(unittest.TestCase):
    def test_document_defines_data_first_navigation_and_compatibility(self):
        document = (ROOT / "docs" / "WORKSPACE_INFORMATION_ARCHITECTURE.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        for label in ("影像訓練", "序列訓練", "表格資料預測"):
            self.assertIn(label, document)
        for stable_id in (
            "sequence_classification",
            "sequence_regression",
            "tabular_classification",
            "tabular_regression",
        ):
            self.assertIn(stable_id, document)
        self.assertIn("XGBoost 是模型選項，不是資料型態", document)
        self.assertIn("不得改寫既有 `task_type`", document)
        self.assertIn("docs/WORKSPACE_INFORMATION_ARCHITECTURE.md", readme)


if __name__ == "__main__":
    unittest.main()
