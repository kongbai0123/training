from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Protocol

from src.model_system.sandbox_gate import (
    APPROVAL_DECISION_NAME,
    APPROVED_EXECUTION_DISABLED,
    DRY_RUN_REPORT_NAME,
    append_sandbox_audit,
    read_source_manifest,
)
from src.model_system.sandbox_policy import (
    build_p2_isolated_dry_run_policy,
    build_p3_dependency_environment_check,
    build_p4_process_runner_enforcement,
)


MOCK_DRY_RUN_REPORT_NAME = "mock_dry_run_report.json"
SANDBOX_DRY_RUN_PLAN_NAME = "sandbox_dry_run_plan.json"
MOCK_DRY_RUN_COMPLETED = "MOCK_DRY_RUN_COMPLETED"
SANDBOX_PLAN_READY = "SANDBOX_PLAN_READY"
BLOCKED_APPROVAL_REQUIRED = "BLOCKED_APPROVAL_REQUIRED"
BLOCKED_APPROVAL_REJECTED = "BLOCKED_APPROVAL_REJECTED"


class SandboxDryRunRunner(Protocol):
    def run(self, import_dir: Path, model: Dict[str, Any]) -> Dict[str, Any]:
        """Run a sandbox dry-run contract. Implementations must not trust user code by default."""


class MockSandboxDryRunRunner:
    """Contract-only dry-run runner.

    This runner intentionally does not import, execute, compile, or spawn anything from
    the custom package. It records the checks a real sandbox runner must satisfy later.
    """

    def run(self, import_dir: Path, model: Dict[str, Any]) -> Dict[str, Any]:
        approval = _read_json(import_dir / APPROVAL_DECISION_NAME)
        if not approval:
            report = self._blocked_report(model, BLOCKED_APPROVAL_REQUIRED, "Sandbox dry-run approval is required before mock runner contract can proceed.")
            self._write_reports(import_dir, report)
            return report
        if approval.get("status") != APPROVED_EXECUTION_DISABLED:
            report = self._blocked_report(model, BLOCKED_APPROVAL_REJECTED, "Sandbox dry-run approval is not approved.")
            self._write_reports(import_dir, report)
            return report

        source_manifest = read_source_manifest(import_dir)
        runtime = source_manifest.get("runtime") if isinstance(source_manifest.get("runtime"), dict) else {}
        entrypoint = runtime.get("entrypoint") or ""
        entrypoint_path = (import_dir / entrypoint).resolve() if entrypoint else None
        entrypoint_exists = bool(entrypoint_path and import_dir.resolve() in entrypoint_path.parents and entrypoint_path.exists() and entrypoint_path.is_file())

        checks = [
            _check("approval_recorded", True, "Approval decision exists, but execution remains disabled."),
            _check("execution_mode_mock", True, "Mock runner does not execute package code."),
            _check("adapter_not_imported", True, "adapter.py was not imported."),
            _check("user_code_not_executed", True, "No user package code was executed."),
            _check("entrypoint_declared", bool(entrypoint), "runtime.entrypoint is declared." if entrypoint else "runtime.entrypoint is missing."),
            _check("entrypoint_file_exists", entrypoint_exists, f"{entrypoint} exists." if entrypoint_exists else f"{entrypoint or 'entrypoint'} file is missing."),
            _check("input_contract_declared", isinstance(source_manifest.get("input_spec"), dict), "input_spec is declared."),
            _check("output_contract_declared", isinstance(source_manifest.get("output_spec"), dict), "output_spec is declared."),
            _check("metrics_contract_optional", True, "metrics contract is optional in mock dry-run."),
            _check("artifact_contract_optional", True, "artifact contract is optional in mock dry-run."),
        ]
        passed = all(item["passed"] for item in checks)
        report = {
            "model_id": model.get("model_id"),
            "display_name": model.get("display_name"),
            "status": MOCK_DRY_RUN_COMPLETED if passed else "MOCK_DRY_RUN_FAILED",
            "created_at": datetime.now().isoformat(),
            "execution_mode": "mock",
            "execution_enabled": False,
            "adapter_imported": False,
            "dry_run_executed": False,
            "user_code_executed": False,
            "checks": checks,
            "warnings": [
                "This is a mock dry-run contract only. No adapter code was executed."
            ],
            "errors": [] if passed else [item["message"] for item in checks if not item["passed"]],
            "next_allowed_action": "implement_real_sandbox_runner" if passed else "fix_package_contract",
        }
        self._write_reports(import_dir, report)
        return report

    def _blocked_report(self, model: Dict[str, Any], status: str, reason: str) -> Dict[str, Any]:
        return {
            "model_id": model.get("model_id"),
            "display_name": model.get("display_name"),
            "status": status,
            "created_at": datetime.now().isoformat(),
            "execution_mode": "mock",
            "execution_enabled": False,
            "adapter_imported": False,
            "dry_run_executed": False,
            "user_code_executed": False,
            "checks": [
                _check("approval_required", False, reason),
                _check("adapter_not_imported", True, "adapter.py was not imported."),
                _check("user_code_not_executed", True, "No user package code was executed."),
            ],
            "warnings": [],
            "errors": [reason],
            "next_allowed_action": "request_or_approve_permissions",
        }

    def _write_reports(self, import_dir: Path, report: Dict[str, Any]) -> None:
        _write_json(import_dir / MOCK_DRY_RUN_REPORT_NAME, report)
        _write_json(import_dir / DRY_RUN_REPORT_NAME, report)
        append_sandbox_audit(import_dir, "mock_dry_run_contract_checked", report)


DEFAULT_SANDBOX_DRY_RUN_RUNNER: SandboxDryRunRunner = MockSandboxDryRunRunner()


def build_sandbox_dry_run_plan(import_dir: Path, model: Dict[str, Any]) -> Dict[str, Any]:
    """Create a non-executable sandbox dry-run plan.

    P1-E defines what a future runner would need, but deliberately does not
    construct a runnable command line or import user code.
    """
    approval = _read_json(import_dir / APPROVAL_DECISION_NAME)
    if approval.get("status") != APPROVED_EXECUTION_DISABLED:
        plan = _blocked_plan(model, BLOCKED_APPROVAL_REQUIRED, "Approved sandbox permission decision is required before a dry-run plan can be prepared.")
        _write_json(import_dir / SANDBOX_DRY_RUN_PLAN_NAME, plan)
        append_sandbox_audit(import_dir, "sandbox_plan_blocked", plan)
        return plan

    source_manifest = read_source_manifest(import_dir)
    runtime = source_manifest.get("runtime") if isinstance(source_manifest.get("runtime"), dict) else {}
    dependency_policy = source_manifest.get("dependency_policy") if isinstance(source_manifest.get("dependency_policy"), dict) else {}
    security = source_manifest.get("security") if isinstance(source_manifest.get("security"), dict) else {}
    entrypoint = runtime.get("entrypoint") or ""
    p3_dependency_check = build_p3_dependency_environment_check(import_dir, source_manifest)

    plan = {
        "model_id": model.get("model_id"),
        "display_name": model.get("display_name"),
        "status": SANDBOX_PLAN_READY,
        "created_at": datetime.now().isoformat(),
        "phase": "P1-E",
        "execution_enabled": False,
        "adapter_imported": False,
        "dry_run_executed": False,
        "user_code_executed": False,
        "runtime": {
            "kind": runtime.get("kind"),
            "entrypoint": entrypoint,
            "entrypoint_path": entrypoint,
            "entrypoint_exists": bool(entrypoint and (import_dir / entrypoint).resolve().is_file()),
        },
        "sandbox_policy": {
            "network_allowed": False,
            "shell_allowed": False,
            "dependency_install_allowed": False,
            "external_filesystem_allowed": False,
            "gpu_allowed": False,
            "write_scope": "staging_only",
            "timeout_seconds": 30,
        },
        "p2_isolated_runner_policy": build_p2_isolated_dry_run_policy(source_manifest),
        "p3_dependency_environment_check": p3_dependency_check,
        "p4_process_runner_enforcement": build_p4_process_runner_enforcement(source_manifest, p3_dependency_check),
        "requested_capabilities": {
            "requires_network": bool(security.get("requires_network")),
            "requires_shell": bool(security.get("requires_shell")),
            "requires_gpu": bool(security.get("requires_gpu")),
            "writes_files": bool(security.get("writes_files")),
            "dependency_install_requested": bool(dependency_policy.get("install_allowed")),
        },
        "contracts": {
            "input_spec_present": isinstance(source_manifest.get("input_spec"), dict),
            "output_spec_present": isinstance(source_manifest.get("output_spec"), dict),
            "metrics_contract_present": isinstance(source_manifest.get("metrics_contract"), dict),
            "artifact_contract_present": isinstance(source_manifest.get("artifact_contract"), dict),
        },
        "blocked_reasons": [
            "P1-E produces a plan only. Adapter import and execution remain disabled.",
            "A future real sandbox runner must implement process isolation before execution is allowed.",
        ],
        "next_allowed_action": "mock_dry_run_contract",
    }
    _write_json(import_dir / SANDBOX_DRY_RUN_PLAN_NAME, plan)
    append_sandbox_audit(import_dir, "sandbox_plan_created", plan)
    return plan


def _check(name: str, passed: bool, message: str) -> Dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "status": "passed" if passed else "failed",
        "message": message,
    }


def _blocked_plan(model: Dict[str, Any], status: str, reason: str) -> Dict[str, Any]:
    return {
        "model_id": model.get("model_id"),
        "display_name": model.get("display_name"),
        "status": status,
        "created_at": datetime.now().isoformat(),
        "phase": "P1-E",
        "execution_enabled": False,
        "adapter_imported": False,
        "dry_run_executed": False,
        "user_code_executed": False,
        "blocked_reasons": [reason],
        "next_allowed_action": "approve_permissions",
    }


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
