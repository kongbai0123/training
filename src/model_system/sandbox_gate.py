from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


APPROVAL_REQUEST_NAME = "sandbox_permission_request.json"
APPROVAL_DECISION_NAME = "sandbox_approval_decision.json"
DRY_RUN_REPORT_NAME = "dry_run_report.json"
SANDBOX_AUDIT_LOG_NAME = "sandbox_audit_log.jsonl"

APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
APPROVED_EXECUTION_DISABLED = "APPROVED_EXECUTION_DISABLED"
APPROVAL_REJECTED = "APPROVAL_REJECTED"
BLOCKED_UNSUPPORTED_RUNTIME = "BLOCKED_UNSUPPORTED_RUNTIME"


def read_source_manifest(import_dir: Path) -> Dict[str, Any]:
    source_manifest = import_dir / "source_model_manifest.json"
    if not source_manifest.exists():
        source_manifest = import_dir / "model_manifest.json"
    if not source_manifest.exists():
        return {}
    try:
        payload = json.loads(source_manifest.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def build_permission_gate(source_manifest: Dict[str, Any]) -> Dict[str, Any]:
    runtime = source_manifest.get("runtime") if isinstance(source_manifest.get("runtime"), dict) else {}
    security = source_manifest.get("security") if isinstance(source_manifest.get("security"), dict) else {}
    dependency_policy = source_manifest.get("dependency_policy") if isinstance(source_manifest.get("dependency_policy"), dict) else {}
    sandbox = source_manifest.get("sandbox") if isinstance(source_manifest.get("sandbox"), dict) else {}
    filesystem = sandbox.get("filesystem") if isinstance(sandbox.get("filesystem"), dict) else {}

    permissions = [
        _permission("python_adapter_execution", True, "high", "Importing adapter code and calling dry-run entrypoint."),
        _permission("network", bool(security.get("requires_network") or sandbox.get("network")), "high", "Network access during dry-run."),
        _permission("shell", bool(security.get("requires_shell") or sandbox.get("shell")), "high", "Shell command execution."),
        _permission("dependency_install", bool(dependency_policy.get("install_allowed")), "high", "Installing package dependencies."),
        _permission("gpu", bool(security.get("requires_gpu") or sandbox.get("gpu_access")), "medium", "GPU access during dry-run."),
        _permission("file_write", bool(security.get("writes_files")), "medium", "Writing files during dry-run."),
        _permission("external_read", _has_external_paths(filesystem.get("read")), "high", "Reading outside project/plugin staging scope."),
        _permission("external_write", _has_external_paths(filesystem.get("write")), "high", "Writing outside project/plugin staging scope."),
    ]
    requested = [item for item in permissions if item["requested"]]
    high_risk = [item for item in requested if item["risk"] == "high"]

    return {
        "runtime_kind": runtime.get("kind"),
        "entrypoint": runtime.get("entrypoint"),
        "approval_required": True,
        "execution_enabled": False,
        "permissions": permissions,
        "requested_permissions": requested,
        "high_risk_permissions": high_risk,
        "policy": {
            "network_default": False,
            "shell_default": False,
            "dependency_install_default": False,
            "external_filesystem_default": False,
            "missing_permissions_are_denied": True,
        },
    }


def build_dry_run_request(import_dir: Path, model: Dict[str, Any], source_manifest: Dict[str, Any]) -> Dict[str, Any]:
    gate = build_permission_gate(source_manifest)
    now = datetime.now().isoformat()
    runtime_supported = gate.get("runtime_kind") == "python_adapter"
    status = APPROVAL_REQUIRED if runtime_supported else BLOCKED_UNSUPPORTED_RUNTIME
    request = {
        "model_id": model.get("model_id"),
        "display_name": model.get("display_name"),
        "status": status,
        "created_at": now,
        "runtime_supported": runtime_supported,
        "approval_required": True,
        "approval_status": "pending" if runtime_supported else "blocked",
        "execution_enabled": False,
        "adapter_imported": False,
        "dry_run_executed": False,
        "permission_gate": gate,
        "blocked_reasons": [
            "Python adapter dry-run requires explicit approval.",
            "Sandbox runner is not enabled in this phase.",
        ] if runtime_supported else [
            "Only runtime.kind=python_adapter can request P1-B dry-run approval.",
            "Sandbox runner is not enabled in this phase.",
        ],
        "next_allowed_action": "approve_or_reject_permissions" if runtime_supported else "fix_manifest_runtime",
    }
    _write_json(import_dir / APPROVAL_REQUEST_NAME, request)
    _write_json(import_dir / DRY_RUN_REPORT_NAME, request)
    append_sandbox_audit(import_dir, "dry_run_permission_requested", request)
    return request


def record_approval_decision(import_dir: Path, model: Dict[str, Any], decision: str, approved_by: str = "local_user", note: str = "") -> Dict[str, Any]:
    normalized = str(decision or "").strip().lower()
    if normalized not in {"approve", "reject"}:
        raise ValueError("decision must be approve or reject")

    status = APPROVED_EXECUTION_DISABLED if normalized == "approve" else APPROVAL_REJECTED
    payload = {
        "model_id": model.get("model_id"),
        "display_name": model.get("display_name"),
        "status": status,
        "decision": normalized,
        "approved_by": approved_by or "local_user",
        "note": note or "",
        "decided_at": datetime.now().isoformat(),
        "execution_enabled": False,
        "adapter_imported": False,
        "dry_run_executed": False,
        "blocked_reasons": [
            "Approval was recorded, but execution remains disabled until sandbox runner is implemented."
        ] if normalized == "approve" else [
            "User rejected sandbox dry-run permissions."
        ],
        "next_allowed_action": "sandbox_runner_required" if normalized == "approve" else "manual_review",
    }
    _write_json(import_dir / APPROVAL_DECISION_NAME, payload)
    _write_json(import_dir / DRY_RUN_REPORT_NAME, payload)
    append_sandbox_audit(import_dir, f"dry_run_permission_{normalized}", payload)
    return payload


def append_sandbox_audit(import_dir: Path, event: str, payload: Dict[str, Any]) -> None:
    record = {
        "event": event,
        "created_at": datetime.now().isoformat(),
        "model_id": payload.get("model_id"),
        "status": payload.get("status"),
        "execution_enabled": bool(payload.get("execution_enabled", False)),
        "adapter_imported": bool(payload.get("adapter_imported", False)),
        "dry_run_executed": bool(payload.get("dry_run_executed", False)),
        "user_code_executed": bool(payload.get("user_code_executed", False)),
    }
    path = import_dir / SANDBOX_AUDIT_LOG_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_sandbox_audit(import_dir: Path) -> List[Dict[str, Any]]:
    path = import_dir / SANDBOX_AUDIT_LOG_NAME
    if not path.exists():
        return []
    records: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            payload = json.loads(line)
            if isinstance(payload, dict):
                records.append(payload)
        except Exception:
            continue
    return records


def _permission(name: str, requested: bool, risk: str, description: str) -> Dict[str, Any]:
    return {
        "name": name,
        "requested": bool(requested),
        "risk": risk,
        "requires_approval": bool(requested),
        "allowed_by_default": False,
        "description": description,
    }


def _has_external_paths(value: Any) -> bool:
    if value is None:
        return False
    values: List[Any] = value if isinstance(value, list) else [value]
    safe_tokens = {"project.dataset", "plugin.package", "project.training.runs.current", "project.models.imports.staging"}
    return any(str(item) not in safe_tokens for item in values)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
