from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional


CONTRACT_VERSION = "1.0"


def utc_now_iso() -> str:
    return datetime.now().isoformat()


def build_backend_contract(
    run_id: str,
    architecture: str,
    backend: str,
    task_type: str,
    status: str,
    created_at: str,
    completed_at: Optional[str] = None,
) -> Dict[str, Any]:
    contract = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "architecture": architecture,
        "backend": backend,
        "task_type": task_type,
        "status": status,
        "created_at": created_at,
        "completed_at": completed_at,
        "generated_at": utc_now_iso(),
    }
    return contract
