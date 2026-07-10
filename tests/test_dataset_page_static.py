import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DatasetPageStaticTests(unittest.TestCase):
    def test_class_input_only_commits_on_enter_or_add_button(self):
        dataset_js = (ROOT / "static" / "pages" / "dataset.js").read_text(encoding="utf-8")

        self.assertIn('if (event.key !== "Enter") return;', dataset_js)
        self.assertNotIn('["Enter", ",", ";"].includes(event.key)', dataset_js)
        self.assertIn("function parseClassTokens(rawValue)", dataset_js)
        self.assertIn(".split(/[,;]+/)", dataset_js)


if __name__ == "__main__":
    unittest.main()
