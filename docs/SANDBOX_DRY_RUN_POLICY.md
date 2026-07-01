# Sandbox Dry-Run Policy

Status: P2 design only

This document defines the policy for a future real isolated dry-run runner. P2 does not execute custom adapters.

## Objective

Prepare the contract for running a Python adapter dry-run in a separate isolated process later.

P2 output is a policy contract, not an execution feature.

## Execution Boundary

P2 must keep these flags false:

```json
{
  "execution_enabled": false,
  "adapter_imported": false,
  "dry_run_executed": false,
  "user_code_executed": false
}
```

## Future Runner Shape

The future runner must use a separate process:

```text
main app
  -> sandbox runner controller
    -> isolated worker process
      -> load adapter only after approval and preflight pass
```

The worker process must receive only:

```text
1. package staging directory
2. source_model_manifest.json
3. generated sample input
4. output directory inside staging or run temp scope
5. timeout and resource limits
```

## Required Controls

Before real execution is allowed, all controls must exist:

```text
separate_process
timeout_seconds
staging_workdir
read_only_package_mount
write_only_run_output_dir
stdout_json_contract
stderr_capture
resource_limits
audit_log
user_approval_record
```

## Default Deny Policy

The default policy is deny:

```text
network: denied
shell: denied
dependency install: denied
GPU: denied
external filesystem read: denied
external filesystem write: denied
package source write: denied
```

## Worker I/O Contract

The future worker must emit JSON:

```json
{
  "status": "passed",
  "adapter_loaded": true,
  "dry_run_executed": true,
  "input_contract": {},
  "output_contract": {},
  "metrics_contract": {},
  "artifact_contract": {},
  "warnings": [],
  "errors": []
}
```

The main app must treat invalid JSON, timeout, non-zero exit code, or missing output as failure.

## Hard Non-Goals In P2

```text
Do not import adapter.py
Do not spawn Python
Do not compile C/C++
Do not run infer.exe
Do not install dependencies
Do not add custom package to training selector
Do not enable inference
Do not mark package ENABLED
```

## Phase Sequence

Remaining path:

```text
P2: real isolated dry-run runner design
P3: dependency lock / offline environment check
P4: sandboxed process runner enforcement
P5: dry-run passed registry enablement policy
P6: limited inference / training integration
```

## P3 Dependency Lock / Offline Environment Check

P3 inspects dependency metadata only. It must not install or import anything.

P3 checks:

```text
runtime.kind declared
dependency installation disabled
offline mode required
requirements file exists if declared
lock file exists if declared
```

P3 output is embedded in `sandbox_dry_run_plan.json`:

```text
p3_dependency_environment_check
```

Required safety flags:

```json
{
  "execution_enabled": false,
  "dependency_install_executed": false,
  "network_used": false
}
```

## P5 Registry Enablement Policy

P5 decides whether a custom package may move from `REGISTERED_DISABLED` toward
manual enablement review.

Current rule:

```text
Mock dry-run is not sufficient.
Only a future REAL_DRY_RUN_PASSED report can make a package eligible.
```

P5 output:

```text
registry_enablement_policy.json
```

Default P5 result before real dry-run:

```json
{
  "status": "P5_ENABLEMENT_BLOCKED",
  "execution_enabled": false,
  "eligible_for_registry_enablement": false,
  "allowed_registry_status": "REGISTERED_DISABLED"
}
```

## P6 Limited Integration Contract

P6 describes how a package would appear in selectors after P5 review passes.

Current rule:

```text
If P5 is blocked, hide package from training, inference, and evaluation selectors.
```

P6 output:

```text
limited_integration_contract.json
```

Default P6 result before enablement:

```json
{
  "status": "P6_LIMITED_INTEGRATION_BLOCKED",
  "execution_enabled": false,
  "selector_visibility": {
    "training_selector": false,
    "inference_selector": false,
    "evaluation_selector": false
  }
}
```

## P7 Sandbox Worker Threat Model

P7 is a design-only phase for the future real sandbox worker prototype.

Reference:

```text
docs/SANDBOX_THREAT_MODEL_P7.md
```

P7 must define:

```text
assets to protect
trust boundaries
threat categories
worker restrictions
approval gates
failure policy
future implementation acceptance gates
```

P7 must not execute:

```text
adapter.py
train.py
preprocess.py
postprocess.py
src/*.py
src/*.c
src/*.cpp
bin/*.exe
```

## P4 Sandboxed Process Runner Enforcement

P4 defines enforcement requirements for a future process runner. It still does
not spawn a process.

Required controls:

```text
separate_process
timeout_enforced
cwd_is_staging
package_read_only
output_dir_write_only
stdout_json_required
stderr_captured
network_disabled
shell_disabled
dependency_install_disabled
external_filesystem_disabled
```

P4 output is embedded in `sandbox_dry_run_plan.json`:

```text
p4_process_runner_enforcement
```

Required safety flags:

```json
{
  "execution_enabled": false,
  "process_spawned": false,
  "adapter_imported": false,
  "dry_run_executed": false,
  "user_code_executed": false
}
```
