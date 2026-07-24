from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.update.package_builder import build_update_package
from src.update.versioning import load_version_info


def _read_optional(path: Path | None) -> str:
    return path.read_text(encoding="utf-8") if path and path.is_file() else ""


def main() -> int:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    parser = argparse.ArgumentParser(description="Build a signed Vision Training Studio update package.")
    parser.add_argument("--dist", type=Path, default=Path("dist/VisionTrainingStudio"))
    parser.add_argument("--version-file", type=Path, default=Path("version.json"))
    parser.add_argument("--baseline", type=Path)
    parser.add_argument(
        "--private-key",
        type=Path,
        default=local_app_data / "VisionTrainingStudio" / "release_keys" / "update_private_key.pem",
    )
    parser.add_argument("--release-notes-zh", type=Path)
    parser.add_argument("--release-notes-en", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    version = load_version_info(args.version_file)
    baseline = args.baseline or Path("updates/baselines") / f"runtime-{version.runtime_version}.json"
    output = args.output or Path("release_artifacts") / (
        f"VisionTrainingStudio_Update_{version.app_version}_runtime-{version.runtime_version}.vtsupdate"
    )
    result = build_update_package(
        dist=args.dist,
        baseline_path=baseline,
        version_file=args.version_file,
        private_key_path=args.private_key,
        output=output,
        release_notes_zh=_read_optional(args.release_notes_zh),
        release_notes_en=_read_optional(args.release_notes_en),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
