from __future__ import annotations

import argparse
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.update.transaction import apply_update, prepare_update
from src.update.storage import cleanup_update_storage


def process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        synchronize = 0x00100000
        wait_object_0 = 0x00000000
        wait_timeout = 0x00000102
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel32.WaitForSingleObject.restype = ctypes.c_uint32
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            error = ctypes.get_last_error()
            if error == 5:
                return True
            return False
        try:
            result = kernel32.WaitForSingleObject(handle, 0)
            if result == wait_timeout:
                return True
            if result == wait_object_0:
                return False
            raise OSError(ctypes.get_last_error(), "Could not query application process state.")
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_for_process_exit(pid: int, timeout_seconds: float = 60.0) -> None:
    if pid <= 0:
        return
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not process_is_running(pid):
            return
        time.sleep(0.25)
    raise TimeoutError("The application did not close in time. The update was not applied.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply a signed Vision Training Studio update.")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--install-dir", type=Path, required=True)
    parser.add_argument("--current-version-file", type=Path, required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--update-root", type=Path, required=True)
    parser.add_argument("--parent-pid", type=int, default=0)
    parser.add_argument("--no-relaunch", action="store_true")
    args = parser.parse_args()

    journal = prepare_update(
        archive=args.archive,
        install_dir=args.install_dir,
        current_version_file=args.current_version_file,
        public_key_path=args.public_key,
        update_root=args.update_root,
    )
    wait_for_process_exit(args.parent_pid)
    result = apply_update(journal)
    if result["state"] != "completed":
        return 2
    cleanup_update_storage(args.update_root)
    executable = args.install_dir / "VisionTrainingStudio.exe"
    if not args.no_relaunch and executable.is_file():
        subprocess.Popen([str(executable)], cwd=str(args.install_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
