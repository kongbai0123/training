from __future__ import annotations

from typing import Any, Dict, Optional


TEST_RUN_MARKERS = ("smoke", "test", "probe", "workers0", "tmp", "debug")


def is_test_run(run_id: str, run: Optional[Dict[str, Any]] = None) -> bool:
    normalized = str(run_id or "").lower()
    if any(marker in normalized for marker in TEST_RUN_MARKERS):
        return True
    if not run:
        return False
    tags = run.get("tags") or run.get("labels") or []
    if isinstance(tags, list) and any(str(tag).lower() in TEST_RUN_MARKERS for tag in tags):
        return True
    note = str(run.get("note") or run.get("description") or "").lower()
    return any(marker in note for marker in TEST_RUN_MARKERS)
