import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import launcher
from src.startup_splash import StartupSplash, should_show_startup_splash


class StartupSplashTests(unittest.TestCase):
    def test_headless_shell_skips_native_splash(self):
        self.assertFalse(should_show_startup_splash("none"))

    def test_environment_can_disable_splash_for_automation(self):
        with patch.dict(os.environ, {"VTS_DISABLE_SPLASH": "true"}):
            self.assertFalse(should_show_startup_splash("webview"))

    def test_desktop_shell_enables_splash_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(should_show_startup_splash("webview"))
            self.assertTrue(should_show_startup_splash("browser"))

    def test_disabled_splash_methods_are_safe_noops(self):
        splash = StartupSplash(enabled=False)
        splash.update_status(0, "status", "detail", 0.5, elapsed_seconds=8)
        splash.complete()
        splash.show_error("error")
        splash.wait_for_dismiss(0)
        splash.close()
        self.assertFalse(splash.enabled)

    def test_readiness_probe_reports_wait_progress(self):
        callbacks = []

        class ReadyResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        with patch("launcher.urlopen", return_value=ReadyResponse()):
            ready = launcher.wait_ready(
                "http://127.0.0.1:1/api/health",
                timeout_sec=1,
                on_wait=lambda elapsed, error: callbacks.append((elapsed, error)),
            )

        self.assertTrue(ready)
        self.assertEqual(len(callbacks), 1)
        self.assertIsNone(callbacks[0][1])

    def test_early_launcher_failure_exits_cleanly_without_gui(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(sys, "argv", ["launcher.py", "--shell", "none"]),
                patch.object(launcher, "LOGS_DIR", Path(temp_dir)),
                patch("launcher.next_available_port", side_effect=RuntimeError("no port")),
                self.assertRaises(SystemExit) as raised,
            ):
                launcher.main()

        self.assertEqual(raised.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
