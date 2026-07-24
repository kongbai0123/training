from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.update.security import sha256_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Create release SHA-256 checksums.")
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    entries: list[str] = []
    for path in args.files:
        path = path.resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        entries.append(f"{sha256_file(path)}  {path.name}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(entries) + "\n", encoding="utf-8")
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
