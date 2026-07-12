import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ActionGuardStaticTests(unittest.TestCase):
    def test_guarded_actions_remain_clickable_and_use_dialog(self):
        availability = (ROOT / "static" / "core" / "action_availability.js").read_text(encoding="utf-8")
        guard = (ROOT / "static" / "core" / "action_guard.js").read_text(encoding="utf-8")
        bootstrap = (ROOT / "static" / "core" / "bootstrap.js").read_text(encoding="utf-8")
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

        self.assertIn("el.disabled = false", availability)
        self.assertNotIn("el.disabled = !rules[requirement]", availability)
        self.assertIn('document.addEventListener("click", interceptGuardedAction, true)', guard)
        self.assertIn("evaluateActionRequirement", guard)
        self.assertIn("initActionGuard();", bootstrap)
        self.assertIn('id="action-guard-modal"', html)

    def test_primary_operations_use_soft_readiness_blocks(self):
        training = (ROOT / "static" / "pages" / "training.js").read_text(encoding="utf-8")
        rnn = (ROOT / "static" / "pages" / "training_modes.js").read_text(encoding="utf-8")
        inference = (ROOT / "static" / "pages" / "inference.js").read_text(encoding="utf-8")
        export = (ROOT / "static" / "pages" / "export.js").read_text(encoding="utf-8")
        augmentation = (ROOT / "static" / "pages" / "augmentation.js").read_text(encoding="utf-8")

        self.assertIn("startBtn.disabled = isRunning || isStopping", training)
        self.assertIn('button.dataset.blockReason = !canStart && !operationBusy ? titleMessage : ""', rnn)
        self.assertIn("btn.disabled = running", inference)
        self.assertIn("button.disabled = !visible", export)
        self.assertIn("previewBtn.disabled = applying", augmentation)
        self.assertIn("applyBtn.disabled = applying", augmentation)


if __name__ == "__main__":
    unittest.main()
