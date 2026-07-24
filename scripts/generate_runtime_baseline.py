from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.update.baseline import build_runtime_baseline
from src.update.versioning import load_version_info


def main() -> int:
    parser = argparse.ArgumentParser(description="Hash a validated Windows distribution as a runtime baseline.")
    parser.add_argument("--dist", type=Path, default=Path("dist/VisionTrainingStudio"))
    parser.add_argument("--version-file", type=Path, default=Path("version.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    version = load_version_info(args.version_file)
    output = args.output or Path("updates/baselines") / f"runtime-{version.runtime_version}.json"
    result = build_runtime_baseline(args.dist, args.version_file, output)
    print(
        json.dumps(
            {
                "output": output.resolve().as_posix(),
                "runtime_version": result["runtime_version"],
                "file_count": result["file_count"],
                "runtime_file_count": result["runtime_file_count"],
                "app_file_count": result["app_file_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
