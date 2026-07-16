from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from src.app_paths import CONFIG_DIR


ONBOARDING_SCHEMA_VERSION = 1
ONBOARDING_STATE_PATH = CONFIG_DIR / "onboarding.json"


def get_onboarding_state(path: Path | None = None) -> dict[str, Any]:
    state_path = path or ONBOARDING_STATE_PATH
    default = {
        "schema_version": ONBOARDING_SCHEMA_VERSION,
        "initial_setup_completed": False,
        "completed_at": None,
        "outcome": None,
    }
    if not state_path.is_file():
        return default
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default
    if not isinstance(payload, dict):
        return default
    return {
        **default,
        "initial_setup_completed": bool(payload.get("initial_setup_completed")),
        "completed_at": payload.get("completed_at"),
        "outcome": payload.get("outcome"),
    }


def complete_onboarding(outcome: str, path: Path | None = None) -> dict[str, Any]:
    state_path = path or ONBOARDING_STATE_PATH
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": ONBOARDING_SCHEMA_VERSION,
        "initial_setup_completed": True,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "outcome": outcome if outcome in {"completed", "installed", "skipped", "migrated"} else "completed",
    }
    temporary_path = state_path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary_path.replace(state_path)
    return payload
