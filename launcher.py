#!/usr/bin/env python
from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Optional, Tuple
from urllib.request import urlopen

from src.app_paths import LOGS_DIR


APP_TITLE = "Vision Training Studio"


def run_backend_child(host: str, port: int, env_mode: str) -> None:
    import os

    os.environ["VTS_ENV"] = env_mode
    import uvicorn
    from app import app as fastapi_app

    uvicorn.run(fastapi_app, host=host, port=port, log_level="info")


def open_desktop_window(url: str, backend_process: subprocess.Popen) -> None:
    try:
        import webview

        def on_closed():
            if backend_process and backend_process.poll() is None:
                backend_process.terminate()

        window = webview.create_window(
            APP_TITLE,
            url,
            width=1920,
            height=1080,
            min_size=(1280, 720),
            resizable=True,
            confirm_close=True,
        )
        window.events.closed += on_closed
        webview.start(gui="edgechromium", debug=False)
    except Exception as exc:
        print(f"[launcher] Desktop shell failed, falling back to browser: {exc}")
        webbrowser.open(url)
        while True:
            if backend_process.poll() is not None:
                raise RuntimeError("Backend process exited unexpectedly.")
            time.sleep(1)


def is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def next_available_port(host: str, preferred: int, max_delta: int = 30) -> int:
    for port in range(preferred, preferred + max_delta + 1):
        if is_port_available(host, port):
            return port
    raise RuntimeError(f"No available ports in range {preferred}-{preferred + max_delta}")


def wait_ready(url: str, timeout_sec: int = 20) -> bool:
    deadline = time.time() + timeout_sec
    last_error: Optional[str] = None
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=1) as rsp:
                if 200 <= getattr(rsp, "status", 0) < 300:
                    return True
        except Exception as exc:
            last_error = str(exc)
            time.sleep(0.7)
    if last_error:
        print(f"[launcher] Backend ready check failed: {last_error}")
    return False


def run_backend(host: str, port: int, env_mode: str, cwd: Path, log_path: Path) -> Tuple[subprocess.Popen, object]:
    env = dict(**{**os_env(), "VTS_ENV": env_mode})
    if getattr(sys, "frozen", False):
        cmd = [
            sys.executable,
            "--backend-child",
            "--host",
            host,
            "--port",
            str(port),
            "--env",
            env_mode,
        ]
    else:
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "app:app",
            "--host",
            host,
            "--port",
            str(port),
            "--log-level",
            "info",
        ]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("a", encoding="utf-8")
    process = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    return process, log_file


def os_env() -> dict:
    return dict(__import__("os").environ)


def parse_args():
    parser = argparse.ArgumentParser(description="Vision Training Studio launcher")
    parser.add_argument("--backend-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--host", default="127.0.0.1", help="Backend bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=18080, help="Preferred bind port")
    parser.add_argument("--shell", default="webview", choices=["webview", "browser", "none"], help="Desktop shell mode")
    parser.add_argument("--open-browser", action="store_true", default=False, help="Deprecated: open browser after startup")
    parser.add_argument("--no-open-browser", action="store_true", help="Do not open browser")
    parser.add_argument("--env", default="production", choices=["development", "production"], help="Application mode")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.backend_child:
        run_backend_child(args.host, args.port, args.env)
        return

    cwd = Path(__file__).resolve().parent
    shell = "browser" if args.open_browser else args.shell
    if args.no_open_browser:
        shell = "none"
    port = next_available_port(args.host, args.port)
    base_url = f"http://{args.host}:{port}"

    log_dir = LOGS_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "launcher.log"

    print(f"[launcher] Starting Vision Training Studio at {base_url}")
    print(f"[launcher] Logs: {log_path}")
    print(f"[launcher] Working dir: {cwd}")
    proc = None
    backend_log = None
    proc, backend_log = run_backend(args.host, port, args.env, cwd, log_path)
    try:
        if not wait_ready(f"{base_url}/api/health", timeout_sec=25):
            raise RuntimeError("Backend did not become healthy in time.")

        if backend_log:
            backend_log.write(f"Backend started at {base_url}\\n")
            backend_log.flush()

        if shell == "webview":
            open_desktop_window(base_url, proc)
            return_code = 0
            return
        elif shell == "browser":
            webbrowser.open(base_url)
            print(f"[launcher] Browser opened: {base_url}")
        else:
            print(f"[launcher] Backend ready: {base_url}")

        while True:
            if proc.poll() is not None:
                raise RuntimeError("Backend process exited unexpectedly.")
            time.sleep(1)
    except KeyboardInterrupt:
        print("[launcher] Keyboard interrupt, shutting down.")
    except Exception as exc:
        print(f"[launcher] {exc}")
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"[launcher] {exc}\\n")
        return_code = 1
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
        if backend_log:
            backend_log.close()

    return_code = locals().get("return_code", 0)
    raise SystemExit(return_code)


if __name__ == "__main__":
    # PyInstaller DataLoader workers start by re-entering this executable.
    # Let multiprocessing consume its private spawn arguments before our
    # application argument parser sees them.
    import multiprocessing

    multiprocessing.freeze_support()
    main()
