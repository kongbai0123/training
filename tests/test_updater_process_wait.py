from __future__ import annotations

import os
import subprocess
import sys
import unittest

from updater.updater import process_is_running, wait_for_process_exit


class UpdaterProcessWaitTests(unittest.TestCase):
    def test_current_process_is_reported_running(self):
        self.assertTrue(process_is_running(os.getpid()))

    def test_wait_returns_after_child_process_exits(self):
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(0.25)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.assertTrue(process_is_running(child.pid))
        wait_for_process_exit(child.pid, timeout_seconds=3)
        child.wait(timeout=1)
        self.assertFalse(process_is_running(child.pid))

    def test_wait_times_out_for_live_process(self):
        with self.assertRaises(TimeoutError):
            wait_for_process_exit(os.getpid(), timeout_seconds=0.05)


if __name__ == "__main__":
    unittest.main()
