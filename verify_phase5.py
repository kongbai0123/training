import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request_json(url: str, timeout: float = 2.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_health(base_url: str, timeout_seconds: float = 20.0) -> dict:
    deadline = time.time() + timeout_seconds
    last_error = None
    while time.time() < deadline:
        try:
            return request_json(f"{base_url}/api/health")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(0.25)
    raise RuntimeError(f"health endpoint did not become ready: {last_error}")


def assert_health_schema(payload: dict, expected_base_dir: Path | None = None) -> None:
    assert payload["status"] == "healthy", payload

    device = payload["device"]
    assert isinstance(device["has_gpu"], bool), device
    assert isinstance(device["device_name"], str) and device["device_name"], device
    assert isinstance(device["torch_version"], str) and device["torch_version"], device

    directories = payload["directories"]
    for key in ("base_dir", "projects_dir", "static_dir"):
        assert isinstance(directories[key], str) and directories[key], directories
        assert Path(directories[key]).is_absolute(), directories

    if expected_base_dir is not None:
        expected = expected_base_dir.resolve().as_posix()
        assert directories["base_dir"] == expected, directories
        assert directories["projects_dir"] == (expected_base_dir / "projects").resolve().as_posix(), directories
        assert directories["static_dir"] == (expected_base_dir / "static").resolve().as_posix(), directories


def start_server(cwd: Path, port: int, base_dir: Path | None = None) -> subprocess.Popen:
    env = os.environ.copy()
    if base_dir is None:
        env.pop("VTS_BASE_DIR", None)
    else:
        env["VTS_BASE_DIR"] = str(base_dir)
    env["PYTHONPATH"] = str(REPO_ROOT)

    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def stop_server(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def post_json(url: str, payload: dict, timeout: float = 5.0) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def verify_server(cwd: Path, expected_base_dir: Path, env_base_dir: Path | None = None, create_project: bool = False) -> None:
    port = free_port()
    process = start_server(cwd, port, env_base_dir)
    try:
        health = wait_for_health(f"http://127.0.0.1:{port}")
        assert_health_schema(health, expected_base_dir=expected_base_dir)
        print(f"[ok] /api/health schema is valid for {expected_base_dir}")

        assert (expected_base_dir / "projects").is_dir(), "projects directory was not created"
        assert (expected_base_dir / "static").is_dir(), "static directory was not created"
        print(f"[ok] base directories exist under {expected_base_dir}")

        if create_project:
            project = post_json(
                f"http://127.0.0.1:{port}/api/projects",
                {
                    "project_name": "phase5_smoke",
                    "task_type": "semantic_segmentation",
                    "class_names": ["road"],
                },
            )
            project_path = expected_base_dir / "projects" / project["project_id"]
            assert project_path.is_dir(), f"project directory not created: {project_path}"
            assert str(project_path.resolve()).startswith(str((expected_base_dir / "projects").resolve())), project_path
            print("[ok] project creation uses configured projects directory")
    finally:
        stop_server(process)


def run() -> None:
    verify_server(REPO_ROOT, REPO_ROOT)

    temp_root = Path(tempfile.mkdtemp(prefix="vts_phase5_"))
    temp_base = temp_root / "custom_base"
    foreign_cwd = temp_root / "foreign_cwd"
    foreign_cwd.mkdir(parents=True, exist_ok=True)
    try:
        verify_server(foreign_cwd, temp_base, env_base_dir=temp_base, create_project=True)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    print("Phase 5 verification passed.")


if __name__ == "__main__":
    run()
