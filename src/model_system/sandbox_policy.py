from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


P2_POLICY_VERSION = "p2.real_isolated_dry_run.design.1"
P3_POLICY_VERSION = "p3.dependency_lock_offline_environment.1"
P4_POLICY_VERSION = "p4.sandboxed_process_runner_enforcement.1"
P5_POLICY_VERSION = "p5.registry_enablement_policy.1"
P6_POLICY_VERSION = "p6.limited_integration_contract.1"


@dataclass(frozen=True)
class SandboxPolicyDecision:
    status: str
    execution_enabled: bool
    allowed: Dict[str, bool]
    required_controls: List[str]
    blocked_reasons: List[str]
    next_allowed_action: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy_version": P2_POLICY_VERSION,
            "status": self.status,
            "execution_enabled": self.execution_enabled,
            "allowed": dict(self.allowed),
            "required_controls": list(self.required_controls),
            "blocked_reasons": list(self.blocked_reasons),
            "next_allowed_action": self.next_allowed_action,
        }


def build_p2_isolated_dry_run_policy(source_manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Return the P2 policy design for a future real isolated dry-run.

    This is intentionally a policy contract only. It must not import, execute,
    spawn, compile, install, or validate user package code at runtime.
    """
    runtime = source_manifest.get("runtime") if isinstance(source_manifest.get("runtime"), dict) else {}
    security = source_manifest.get("security") if isinstance(source_manifest.get("security"), dict) else {}
    dependency_policy = source_manifest.get("dependency_policy") if isinstance(source_manifest.get("dependency_policy"), dict) else {}

    runtime_supported = runtime.get("kind") == "python_adapter"
    requested_network = bool(security.get("requires_network"))
    requested_shell = bool(security.get("requires_shell"))
    requested_dependency_install = bool(dependency_policy.get("install_allowed"))
    requested_external_write = bool(security.get("writes_files"))

    blocked_reasons = [
        "P2 is design and policy only. Real adapter execution is not implemented.",
        "A separate isolated process runner is required before any user code can run.",
    ]
    if not runtime_supported:
        blocked_reasons.append("Only runtime.kind=python_adapter is eligible for future isolated dry-run.")
    if requested_network:
        blocked_reasons.append("Network access is denied by default.")
    if requested_shell:
        blocked_reasons.append("Shell access is denied by default.")
    if requested_dependency_install:
        blocked_reasons.append("Dependency installation is denied in P2.")
    if requested_external_write:
        blocked_reasons.append("File writes are limited to staging/run output scope.")

    decision = SandboxPolicyDecision(
        status="P2_POLICY_DESIGNED",
        execution_enabled=False,
        allowed={
            "adapter_import": False,
            "python_subprocess": False,
            "network": False,
            "shell": False,
            "dependency_install": False,
            "gpu": False,
            "external_filesystem_read": False,
            "external_filesystem_write": False,
            "write_staging": False,
        },
        required_controls=[
            "separate_process",
            "timeout_seconds",
            "staging_workdir",
            "read_only_package_mount",
            "write_only_run_output_dir",
            "stdout_json_contract",
            "stderr_capture",
            "resource_limits",
            "audit_log",
            "user_approval_record",
        ],
        blocked_reasons=blocked_reasons,
        next_allowed_action="p3_dependency_lock_offline_environment_check",
    )
    payload = decision.to_dict()
    payload["runtime_supported"] = runtime_supported
    payload["requested_permissions"] = {
        "network": requested_network,
        "shell": requested_shell,
        "dependency_install": requested_dependency_install,
        "external_write": requested_external_write,
    }
    return payload


def build_p3_dependency_environment_check(import_dir: Path, source_manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Validate dependency policy metadata without installing anything."""
    dependency_policy = source_manifest.get("dependency_policy") if isinstance(source_manifest.get("dependency_policy"), dict) else {}
    runtime = source_manifest.get("runtime") if isinstance(source_manifest.get("runtime"), dict) else {}

    install_allowed = bool(dependency_policy.get("install_allowed"))
    requirements_file = dependency_policy.get("requirements_file")
    lock_file = dependency_policy.get("lock_file")
    offline_required = dependency_policy.get("offline_required", True)

    checks = [
        _policy_check("runtime_declared", bool(runtime.get("kind")), "runtime.kind is declared."),
        _policy_check("dependency_install_disabled", not install_allowed, "Dependency installation must be disabled."),
        _policy_check("offline_required", bool(offline_required), "Offline mode must be required before sandbox dry-run."),
    ]
    if requirements_file:
        checks.append(_policy_check(
            "requirements_file_exists",
            _inside_and_exists(import_dir, str(requirements_file)),
            f"{requirements_file} exists inside package staging.",
        ))
    else:
        checks.append(_policy_check("requirements_file_optional", True, "No requirements file declared."))

    if lock_file:
        checks.append(_policy_check(
            "lock_file_exists",
            _inside_and_exists(import_dir, str(lock_file)),
            f"{lock_file} exists inside package staging.",
        ))
    else:
        checks.append(_policy_check("lock_file_missing", False, "No dependency lock file declared."))

    passed = all(item["passed"] for item in checks)
    return {
        "policy_version": P3_POLICY_VERSION,
        "status": "P3_DEPENDENCY_CHECK_PASSED" if passed else "P3_DEPENDENCY_CHECK_BLOCKED",
        "execution_enabled": False,
        "dependency_install_executed": False,
        "network_used": False,
        "offline_required": bool(offline_required),
        "checks": checks,
        "blocked_reasons": [] if passed else [item["message"] for item in checks if not item["passed"]],
        "next_allowed_action": "p4_sandboxed_process_runner_enforcement" if passed else "fix_dependency_lock_policy",
    }


def build_p4_process_runner_enforcement(source_manifest: Dict[str, Any], p3_check: Dict[str, Any]) -> Dict[str, Any]:
    """Define the process runner enforcement contract without spawning a process."""
    runtime = source_manifest.get("runtime") if isinstance(source_manifest.get("runtime"), dict) else {}
    p3_passed = p3_check.get("status") == "P3_DEPENDENCY_CHECK_PASSED"
    controls = {
        "separate_process": True,
        "timeout_enforced": True,
        "cwd_is_staging": True,
        "package_read_only": True,
        "output_dir_write_only": True,
        "stdout_json_required": True,
        "stderr_captured": True,
        "network_disabled": True,
        "shell_disabled": True,
        "dependency_install_disabled": True,
        "external_filesystem_disabled": True,
    }
    return {
        "policy_version": P4_POLICY_VERSION,
        "status": "P4_RUNNER_ENFORCEMENT_READY" if p3_passed else "P4_RUNNER_ENFORCEMENT_BLOCKED",
        "execution_enabled": False,
        "process_spawned": False,
        "adapter_imported": False,
        "dry_run_executed": False,
        "user_code_executed": False,
        "runtime_kind": runtime.get("kind"),
        "entrypoint": runtime.get("entrypoint"),
        "controls": controls,
        "blocked_reasons": [
            "P4 defines enforcement only. Process execution remains disabled.",
        ] if p3_passed else [
            "P3 dependency lock / offline check has not passed.",
            "P4 defines enforcement only. Process execution remains disabled.",
        ],
        "next_allowed_action": "p5_registry_enablement_policy" if p3_passed else "fix_p3_dependency_lock_policy",
    }


def build_p5_registry_enablement_policy(
    model: Dict[str, Any],
    dry_run_report: Dict[str, Any],
    sandbox_plan: Dict[str, Any],
) -> Dict[str, Any]:
    """Decide whether a custom package may move toward registry enablement.

    P5 only defines policy. In the current implementation mock dry-runs are not
    enough to enable a model.
    """
    real_dry_run_passed = dry_run_report.get("status") == "REAL_DRY_RUN_PASSED"
    p3_passed = sandbox_plan.get("p3_dependency_environment_check", {}).get("status") == "P3_DEPENDENCY_CHECK_PASSED"
    p4_ready = sandbox_plan.get("p4_process_runner_enforcement", {}).get("status") == "P4_RUNNER_ENFORCEMENT_READY"
    execution_safe = all([
        dry_run_report.get("adapter_imported") is True,
        dry_run_report.get("dry_run_executed") is True,
        dry_run_report.get("user_code_executed") is True,
    ]) if real_dry_run_passed else False

    blocked_reasons: List[str] = []
    if not real_dry_run_passed:
        blocked_reasons.append("A real isolated dry-run has not passed. Mock dry-run is not sufficient for enablement.")
    if not p3_passed:
        blocked_reasons.append("P3 dependency lock / offline environment check has not passed.")
    if not p4_ready:
        blocked_reasons.append("P4 sandboxed process runner enforcement is not ready.")
    if not execution_safe:
        blocked_reasons.append("No verified real execution result is available for registry enablement.")

    eligible = real_dry_run_passed and p3_passed and p4_ready and execution_safe
    capabilities = model.get("capabilities") if isinstance(model.get("capabilities"), dict) else {}
    return {
        "policy_version": P5_POLICY_VERSION,
        "model_id": model.get("model_id"),
        "status": "P5_ENABLEMENT_REVIEW_READY" if eligible else "P5_ENABLEMENT_BLOCKED",
        "execution_enabled": False,
        "eligible_for_registry_enablement": eligible,
        "allowed_registry_status": "READY_FOR_REVIEW" if eligible else "REGISTERED_DISABLED",
        "allowed_capabilities": {
            "train": bool(capabilities.get("train")) if eligible else False,
            "infer": bool(capabilities.get("infer")) if eligible else False,
            "evaluate": bool(capabilities.get("evaluate")) if eligible else False,
        },
        "blocked_reasons": blocked_reasons,
        "next_allowed_action": "manual_enablement_review" if eligible else "run_real_isolated_dry_run",
    }


def build_p6_limited_integration_contract(
    model: Dict[str, Any],
    enablement_policy: Dict[str, Any],
) -> Dict[str, Any]:
    """Describe how a future enabled custom package may integrate with selectors."""
    enabled = enablement_policy.get("status") == "P5_ENABLEMENT_REVIEW_READY"
    allowed = enablement_policy.get("allowed_capabilities") if isinstance(enablement_policy.get("allowed_capabilities"), dict) else {}
    return {
        "policy_version": P6_POLICY_VERSION,
        "model_id": model.get("model_id"),
        "status": "P6_LIMITED_INTEGRATION_READY" if enabled else "P6_LIMITED_INTEGRATION_BLOCKED",
        "execution_enabled": False,
        "selector_visibility": {
            "training_selector": bool(enabled and allowed.get("train")),
            "inference_selector": bool(enabled and allowed.get("infer")),
            "evaluation_selector": bool(enabled and allowed.get("evaluate")),
        },
        "runtime_contract_required": {
            "input_spec": True,
            "output_spec": True,
            "metrics_contract": True,
            "artifact_contract": True,
            "real_dry_run_report": True,
            "audit_log": True,
        },
        "blocked_reasons": [] if enabled else [
            "Registry enablement policy has not approved this package.",
            "Custom package remains hidden from training and inference selectors.",
        ],
        "next_allowed_action": "limited_selector_registration" if enabled else "complete_p5_enablement_policy",
    }


def _policy_check(name: str, passed: bool, message: str) -> Dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "status": "passed" if passed else "failed",
        "message": message,
    }


def _inside_and_exists(root: Path, relative_path: str) -> bool:
    try:
        candidate = (root / relative_path).resolve()
        return root.resolve() in candidate.parents and candidate.is_file()
    except Exception:
        return False
