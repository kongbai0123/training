import unittest

from src.training.state_store import TrainingStateStore


class TrainingStateStorePhase1BTests(unittest.TestCase):
    def setUp(self):
        TrainingStateStore._states.clear()

    def test_init_run_creates_training_state(self):
        state = TrainingStateStore.init_run(
            "project_1",
            "run_1",
            total_epochs=3,
            architecture="cnn",
            backend="ultralytics_yolo",
        )

        self.assertEqual(state["status"], "training")
        self.assertEqual(state["epoch"], 0)
        self.assertEqual(state["total_epochs"], 3)
        self.assertEqual(state["metrics"], [])
        self.assertEqual(state["run_id"], "run_1")
        self.assertEqual(state["architecture"], "cnn")
        self.assertEqual(state["backend"], "ultralytics_yolo")
        self.assertTrue(state["started_at"])
        self.assertTrue(state["updated_at"])

    def test_append_epoch_metrics_updates_epoch_and_metrics(self):
        TrainingStateStore.init_run("project_1", "run_1", 2, "cnn", "ultralytics_yolo")

        state = TrainingStateStore.append_epoch_metrics("project_1", {"epoch": 1, "map50": 0.5})

        self.assertEqual(state["epoch"], 1)
        self.assertEqual(len(state["metrics"]), 1)
        self.assertEqual(state["metrics"][0]["map50"], 0.5)

    def test_mark_methods_update_status(self):
        TrainingStateStore.init_run("project_1", "run_1", 2, "cnn", "ultralytics_yolo")
        self.assertEqual(TrainingStateStore.mark_stopping("project_1")["status"], "stopping")
        self.assertEqual(TrainingStateStore.mark_stopped("project_1", "stop")["status"], "stopped")
        self.assertTrue(TrainingStateStore.get_state("project_1")["completed_at"])

        TrainingStateStore.init_run("project_2", "run_2", 2, "cnn", "ultralytics_yolo")
        failed = TrainingStateStore.mark_failed("project_2", "boom")
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["error"], "boom")

        TrainingStateStore.init_run("project_3", "run_3", 2, "cnn", "ultralytics_yolo")
        completed = TrainingStateStore.mark_completed("project_3", best_model="weights/best.pt")
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["best_model"], "weights/best.pt")

        TrainingStateStore.init_run("project_early", "run_early", 80, "cnn", "ultralytics_yolo")
        early = TrainingStateStore.mark_completed(
            "project_early",
            run_id="run_early",
            termination_reason="early_stopping",
        )
        self.assertEqual(early["status"], "completed")
        self.assertEqual(early["termination_reason"], "early_stopping")

    def test_get_state_returns_deep_copy(self):
        TrainingStateStore.init_run("project_1", "run_1", 2, "cnn", "ultralytics_yolo")
        state = TrainingStateStore.append_epoch_metrics("project_1", {"epoch": 1, "map50": 0.5})
        state["metrics"][0]["map50"] = 99

        fresh = TrainingStateStore.get_state("project_1")
        self.assertEqual(fresh["metrics"][0]["map50"], 0.5)

    def test_is_training_only_true_for_training_status(self):
        TrainingStateStore.init_run("project_1", "run_1", 2, "cnn", "ultralytics_yolo")
        self.assertTrue(TrainingStateStore.is_training("project_1"))

        TrainingStateStore.mark_stopping("project_1")
        self.assertFalse(TrainingStateStore.is_training("project_1"))


if __name__ == "__main__":
    unittest.main()
