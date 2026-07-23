from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.update.transaction import apply_update, prepare_update


def wait_for_process_exit(pid: int, timeout_seconds: float = 60.0) -> None:
    if pid <= 0:
        return
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
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
    executable = args.install_dir / "VisionTrainingStudio.exe"
    if not args.no_relaunch and executable.is_file():
        subprocess.Popen([str(executable)], cwd=str(args.install_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
