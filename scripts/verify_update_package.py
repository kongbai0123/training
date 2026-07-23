from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.update.manifest import verify_update_archive


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a signed Vision Training Studio update package.")
    parser.add_argument("archive", type=Path)
    parser.add_argument(
        "--public-key",
        type=Path,
        default=Path("updates/keys/update_public_key.pem"),
    )
    args = parser.parse_args()
    result = verify_update_archive(args.archive, args.public_key)
    print(
        json.dumps(
            {
                "archive": args.archive.resolve().as_posix(),
                "archive_bytes": result.archive_bytes,
                "archive_sha256": result.archive_sha256,
                "target_app_version": result.manifest["target_app_version"],
                "runtime_version": result.manifest["runtime_version"],
                "file_count": len(result.manifest["files"]),
                "signature": "verified",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
