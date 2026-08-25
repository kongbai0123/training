from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Mapping, Optional


# Backend and metric contracts remain at v1.  Artifact metadata evolves on its
# own version boundary so existing readers do not mistake an unchanged backend
# payload for a v2 backend contract.
CONTRACT_VERSION = "1.0"
ARTIFACT_CONTRACT_VERSION = "2.0"


def build_producer_metadata(
    contract_version: str,
    overrides: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Return portable producer metadata for a generated contract.

    ``src.config`` is imported lazily to keep importing the lightweight
    training contract helpers free of runtime/device discovery side effects.
    Callers may provide overrides for deterministic tooling and tests, while
    the contract version always reflects the payload being produced.
    """

    product = "Vision Training Studio"
    app_version = "0.0.0"
    runtime_version = "unknown"
    try:
        from src import config

        product = str(config.VERSION_INFO.get("product") or product)
        app_version = str(config.APP_VERSION or app_version)
        runtime_version = str(config.RUNTIME_VERSION or runtime_version)
    except (ImportError, OSError, TypeError, ValueError):
        # Contract generation must remain best-effort in incomplete or portable
        # runtimes.  The explicit fallback values make that state visible.
        pass

    producer: Dict[str, Any] = {
        "product": product,
        "app_version": app_version,
        "runtime_version": runtime_version,
    }
    if overrides is not None:
        if not isinstance(overrides, Mapping):
            raise TypeError("producer overrides must be a mapping")
        producer.update(dict(overrides))
    producer["contract_version"] = str(contract_version)
    return producer


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
