import threading
import time
import unittest

from src.training.runners.thread_runner import ThreadTrainingJobRunner


class _FakeThread:
    def __init__(self, alive=True):
        self._alive = alive

    def is_alive(self):
        return self._alive


class ThreadTrainingJobRunnerPhase1CTests(unittest.TestCase):
    def tearDown(self):
        time.sleep(0.01)

    def test_start_registers_active_job(self):
        runner = ThreadTrainingJobRunner()
        release = threading.Event()

        result = runner.start("project_1", "run_1", target=release.wait)

        try:
            self.assertTrue(result["started"])
            self.assertTrue(runner.is_running("project_1"))
            snapshot = runner.snapshot()
            self.assertEqual(snapshot["project_1"]["run_id"], "run_1")
            self.assertTrue(snapshot["project_1"]["alive"])
        finally:
            release.set()
            runner._jobs["project_1"]["thread"].join(timeout=2)

    def test_duplicate_start_is_rejected(self):
        runner = ThreadTrainingJobRunner()
        release = threading.Event()

        first = runner.start("project_1", "run_1", target=release.wait)
        second = runner.start("project_1", "run_2", target=lambda: None)

        try:
            self.assertTrue(first["started"])
            self.assertFalse(second["started"])
            self.assertEqual(second["reason"], "already_running")
            self.assertEqual(second["run_id"], "run_1")
        finally:
            release.set()
            runner._jobs["project_1"]["thread"].join(timeout=2)

    def test_cleanup_removes_only_matching_run_id(self):
        runner = ThreadTrainingJobRunner()
        runner._jobs["project_1"] = {
            "project_id": "project_1",
            "run_id": "run_1",
            "thread": _FakeThread(),
            "thread_name": "training-project_1-run_1",
            "started_at": "2026-06-26T00:00:00",
        }

        runner.cleanup("project_1", "other_run")
        self.assertIn("project_1", runner.snapshot())

        runner.cleanup("project_1", "run_1")
        self.assertNotIn("project_1", runner.snapshot())

    def test_cleanup_does_not_remove_newer_run(self):
        runner = ThreadTrainingJobRunner()
        runner._jobs["project_1"] = {
            "project_id": "project_1",
            "run_id": "run_2",
            "thread": _FakeThread(),
            "thread_name": "training-project_1-run_2",
            "started_at": "2026-06-26T00:00:00",
        }

        runner.cleanup("project_1", "run_1")

        snapshot = runner.snapshot()
        self.assertIn("project_1", snapshot)
        self.assertEqual(snapshot["project_1"]["run_id"], "run_2")

    def test_snapshot_does_not_expose_thread_object_and_is_copy_safe(self):
        runner = ThreadTrainingJobRunner()
        runner._jobs["project_1"] = {
            "project_id": "project_1",
            "run_id": "run_1",
            "thread": _FakeThread(),
            "thread_name": "training-project_1-run_1",
            "started_at": "2026-06-26T00:00:00",
        }

        snapshot = runner.snapshot()
        self.assertNotIn("thread", snapshot["project_1"])

        snapshot["project_1"]["run_id"] = "mutated"
        self.assertEqual(runner.snapshot()["project_1"]["run_id"], "run_1")


if __name__ == "__main__":
    unittest.main()
