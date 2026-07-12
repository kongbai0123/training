from __future__ import annotations

import importlib.metadata
import json
import platform
import sys
from pathlib import Path
from typing import Any, Dict, List

from src.model_system.constants import BASE_DIR


REGISTRY_PATH = BASE_DIR / "data" / "model_research_registry.json"


def evaluate_research_candidates(registry_path: Path = REGISTRY_PATH) -> Dict[str, Any]:
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    candidates: List[Dict[str, Any]] = []
    for source in payload.get("candidates") or []:
        candidate = dict(source)
        package = str(candidate.get("package") or "")
        installed_version = ""
        if package:
            try:
                installed_version = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                pass
        blockers = list(candidate.get("blockers") or [])
        if package and not installed_version:
            blockers.append(f"Optional package '{package}' is not installed in the managed runtime.")
        if platform.system() == "Windows" and candidate.get("windows_classifier_declared") is False:
            blockers.append("The upstream package has not declared Windows as a supported operating system.")
        candidate["runtime_evaluation"] = {
            "platform": platform.system(),
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "package_installed": bool(installed_version),
            "installed_version": installed_version,
            "blockers": list(dict.fromkeys(blockers)),
            "execution_enabled": bool(candidate.get("execution_enabled")) and not blockers,
        }
        candidates.append(candidate)
    return {
        "schema_version": payload.get("schema_version", 1),
        "evaluated_at": payload.get("evaluated_at"),
        "candidates": candidates,
    }
