import unittest

from src.training.state_store import TrainingStateStore


class TrainingStateStorePhase1ATests(unittest.TestCase):
    def setUp(self):
        TrainingStateStore._states.clear()

    def test_unknown_project_returns_idle_compatible_state(self):
        state = TrainingStateStore.get("missing")

        self.assertEqual(state["status"], "idle")
        self.assertEqual(state["epoch"], 0)
        self.assertEqual(state["total_epochs"], 0)
        self.assertEqual(state["metrics"], [])
        self.assertEqual(state["error"], "")
        self.assertEqual(state["run_id"], "")
        self.assertIn("hardware", state)

    def test_normalize_preserves_frontend_keys_and_adds_backend_fields(self):
        raw = {
            "status": "training",
            "epoch": 1,
            "total_epochs": 2,
            "metrics": [{"epoch": 1, "map50": 0.5}],
            "error": "",
            "run_id": "run_1",
            "hardware": {"gpu": {"available": True}},
            "best_model": "weights/best.pt",
        }

        state = TrainingStateStore.normalize(raw, architecture="cnn", backend="ultralytics_yolo")

        self.assertEqual(state["status"], "training")
        self.assertEqual(state["epoch"], 1)
        self.assertEqual(state["total_epochs"], 2)
        self.assertEqual(state["metrics"], raw["metrics"])
        self.assertEqual(state["run_id"], "run_1")
        self.assertEqual(state["architecture"], "cnn")
        self.assertEqual(state["backend"], "ultralytics_yolo")
        self.assertEqual(state["best_model"], "weights/best.pt")

    def test_update_from_backend_stores_normalized_state(self):
        state = TrainingStateStore.update_from_backend(
            "project_1",
            {"status": "completed", "run_id": "run_1"},
            architecture="cnn",
            backend="ultralytics_yolo",
        )

        self.assertEqual(state["status"], "completed")
        self.assertEqual(TrainingStateStore.get("project_1")["backend"], "ultralytics_yolo")


if __name__ == "__main__":
    unittest.main()
