"""Fail when a CSS custom property is used without a global definition."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STYLES = ROOT / "static" / "styles"
LOCAL_ALLOWLIST = {"--selection-accent", "--selection-soft", "--selection-border", "--compare-position"}


def main() -> int:
    sources = {path: path.read_text(encoding="utf-8") for path in STYLES.rglob("*.css")}
    definitions = {
        name
        for text in sources.values()
        for name in re.findall(r"(?m)(--[A-Za-z0-9_-]+)\s*:", text)
    }
    uses = {
        name
        for text in sources.values()
        for name in re.findall(r"var\((--[A-Za-z0-9_-]+)", text)
    }
    missing = sorted(uses - definitions - LOCAL_ALLOWLIST)
    if missing:
        print("Undefined CSS tokens: " + ", ".join(missing))
        return 1
    print(f"CSS tokens valid: {len(definitions)} defined, {len(uses)} used")
    return 0


if __name__ == "__main__":
    sys.exit(main())
