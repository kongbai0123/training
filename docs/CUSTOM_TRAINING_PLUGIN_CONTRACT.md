# Custom Training Plugin Contract

Status: Draft contract only
Version: 0.1
Scope: Specification, validation, and future sandbox integration

This document defines the contract for future custom training plugins in Vision Training Studio. It does not enable plugin execution. Current product builds must not import or execute arbitrary `.py`, `train.py`, `model.py`, or external scripts through the normal model import flow.

## 0. Core Decision

Adopt:

```text
Model Package First
Extension Second
```

The platform does not trust `.py`, `.c`, `.cpp`, `.exe`, `.dll`, `.so`, or any source/runtime file by extension alone. The platform only inspects packages that conform to a declared model import contract.

Important rule:

```text
valid import != executable
valid import != trainable
valid import != enabled
```

Phase P1 may only inspect and validate manifests. It must not execute adapter code, compile source code, install dependencies, or register a package as enabled.

## 1. Purpose

Custom Training Plugin support is intended for advanced users who need to bring their own model architecture, training loop, preprocessing, postprocessing, and metric reporting into the platform.

The goal is to support future workflows such as:

- custom CNN training modules
- custom RNN / sequence models
- PyTorch training packages
- TensorFlow training packages
- domain-specific feature pipelines
- future CNN-LSTM / transformer / sensor-fusion trainers

This contract exists to keep those integrations controlled, reproducible, and auditable.

## 2. Non-Goals For Current Phase

The current phase must not implement:

- plugin execution
- Python script execution
- automatic dependency installation
- sandbox runner
- process runner integration
- Docker integration
- UI launch button for custom plugin training
- `/train/start` integration for custom plugins
- loading unknown `.py`, `.pth`, `.ckpt`, or arbitrary checkpoints

The only permitted output of this phase is this contract specification and future validation design.

## 2.1 Phase P1 Name And Boundary

Formal phase name:

```text
Phase P1: Manifest-only Custom Model Package Validation
```

Purpose:

```text
Import package -> safe staging -> inspect manifest -> generate validation report
```

P1 is not a runtime phase. It is only:

```text
PLAN / INSPECT / VALIDATE
```

P1 hard non-goals:

```text
Do not execute adapter.py
Do not import adapter.py
Do not compile .c / .cpp
Do not run infer.exe
Do not install requirements.txt
Do not run setup.py or pyproject build
Do not call /train/start
Do not add package to trainable selector
Do not add package to active inference selector
Do not allow network
Do not allow writes outside staging
```

Maximum P1 status:

```text
READY_FOR_REVIEW
REGISTERED_DISABLED
```

P1 must never promote a package to:

```text
ENABLED
EXECUTABLE
TRAINABLE
```

## 2.2 Four-Level Import Strategy

| Level | Type | P1 Status | Allowed Behavior |
| --- | --- | --- | --- |
| Level 1 | Standard Model File | prioritized | inspect, validate, register according to existing model catalog rules |
| Level 2 | Python Adapter Package | manifest-only | inspect package and generate validation report; no execution |
| Level 3 | External Executable Package | manifest-only | inspect package and I/O contract; do not run executable |
| Level 4 | Source Code Package | experimental / blocked | inspect manifest and build spec only; do not compile |

`.py`, `.c`, and `.cpp` are source or adapter files. They are not model artifacts.

## 3. Required Package Layout

A custom training plugin must be provided as a folder or zip package with this structure:

```text
custom_training_plugin/
  manifest.yaml
  README.md
  model.py
  train.py
  predict.py
  preprocess.py
  postprocess.py
  requirements.txt
  configs/
    default.yaml
  examples/
    sample_input.json
    sample_batch.csv
  weights/
    optional_initial_weights.pt
```

Only `manifest.yaml` is mandatory for contract inspection. Code files are required only when execution is later enabled by a sandboxed runner.

## 3.1 Package Staging Path

Uploaded packages must be staged under the current project only:

```text
projects/{project_id}/models/imports/staging/{import_id}/
```

P1 may write:

```text
projects/{project_id}/models/imports/staging/{import_id}/validation_report.json
```

P1 must not write imported plugin files into:

```text
dist/
build/
app binary directory
user home
system directories
global model directories
```

## 3.2 Safe Zip Extraction

Zip packages must be extracted with Zip Slip protection.

The extractor must reject entries with:

```text
absolute paths
.. path traversal
drive-prefixed paths such as C:\...
UNC paths
symlinks or link-like entries when detectable
empty or reserved Windows filenames
```

Every extracted path must satisfy:

```text
resolved_path starts with resolved_staging_dir
```

If any unsafe entry is detected, extraction must stop and the package must be marked invalid.

## 4. manifest.yaml

The manifest is the source of truth. The platform must not infer plugin behavior from filenames alone.

P1 minimum accepted manifest shape:

```json
{
  "schema_version": "1.0",
  "model_id": "custom_road_seg_v1",
  "model_name": "Custom Road Segmentation",
  "model_type": "cnn",
  "task": "segmentation",
  "runtime": {
    "kind": "python_adapter",
    "entrypoint": "adapter.py"
  },
  "artifacts": {
    "weights": ["weights/model.onnx"],
    "source": ["adapter.py", "preprocess.py", "postprocess.py"]
  },
  "input_spec": {
    "type": "image",
    "shape": [1, 3, 640, 640],
    "dtype": "float32"
  },
  "output_spec": {
    "type": "segmentation_mask",
    "classes": ["asphalt", "cement", "gravel", "forest", "belgian"],
    "format": "mask"
  },
  "capabilities": {
    "train": false,
    "infer": true,
    "evaluate": true
  },
  "security": {
    "requires_network": false,
    "writes_files": false,
    "requires_shell": false,
    "requires_gpu": false
  },
  "dependency_policy": {
    "install_allowed": false,
    "requirements_file": null
  }
}
```

P1 validates fields only. It does not load or execute the declared runtime entrypoint.

```yaml
contract_version: "1.0"

plugin:
  id: custom.sequence.lstm_v1
  name: Custom Sequence LSTM
  version: "0.1.0"
  description: Sequence classification trainer for CSV feature windows.
  author: ""
  license: "internal"

runtime:
  framework: pytorch
  python: ">=3.11,<3.12"
  backend: custom_pytorch
  execution_mode: sandbox_required
  gpu_supported: true
  cpu_supported: true

task:
  architecture: rnn
  task_family: sequence_classification
  supported_task_types:
    - sequence_classification
  trainable: true
  inference_supported: true
  evaluation_supported: true

entrypoints:
  model_class: model.CustomModel
  trainer_class: train.CustomTrainer
  predict_function: predict.predict
  preprocess_function: preprocess.preprocess
  postprocess_function: postprocess.postprocess

input_contract:
  type: csv_feature_sequence
  layout: batch_time_feature
  dtype: float32
  shape:
    batch: dynamic
    time: 32
    features: dynamic
  required_files:
    - sequence_manifest.json
  feature_schema:
    required: true
    path: feature_schema.json

output_contract:
  type: class_probability
  label_encoder:
    required: true
    path: label_encoder.json
  classes:
    source: label_encoder

training_config_schema:
  sequence_length:
    type: int
    default: 32
    min: 2
    max: 4096
  stride:
    type: int
    default: 8
    min: 1
  batch_size:
    type: int
    default: 32
    min: 1
  epochs:
    type: int
    default: 50
    min: 1
    max: 500
  learning_rate:
    type: float
    default: 0.001
    min: 0.000001

dependencies:
  policy: locked
  requirements_file: requirements.txt
  allow_auto_install: false
  allowed_packages:
    - torch
    - numpy
    - pandas
    - scikit-learn
  blocked_packages:
    - subprocess32
    - paramiko

sandbox:
  required: true
  network: false
  shell: false
  filesystem:
    read:
      - project.dataset
      - project.training_config
      - plugin.package
    write:
      - project.training.runs.current
      - project.tmp.current_job
    denied:
      - user_home
      - system_root
      - app_binary_dir
  timeout_seconds: 86400
  max_log_mb: 256
  gpu_access: user_approved

dry_run:
  required: true
  sample_input: examples/sample_batch.csv
  max_duration_seconds: 60
  checks:
    - import_entrypoints
    - validate_config_schema
    - load_model
    - build_dataset_sample
    - run_one_forward_pass
    - verify_output_contract
    - emit_required_metrics

metrics_contract:
  required:
    - train/loss
    - val/loss
  optional:
    - val/accuracy
    - val/macro_f1
    - val/precision
    - val/recall
    - val/mae
    - val/rmse
  primary_metric:
    key: val/macro_f1
    display_name: Macro-F1
    goal: maximize

artifact_contract:
  required:
    - role: best_model
      type: model_weight
      path: weights/best.pt
    - role: last_model
      type: model_weight
      path: weights/last.pt
    - role: metrics
      type: metrics_jsonl
      path: metrics.jsonl
    - role: summary
      type: run_summary
      path: run_summary.json
  optional:
    - role: feature_schema
      type: feature_schema
      path: preprocess/feature_schema.json
    - role: label_encoder
      type: label_encoder
      path: preprocess/label_encoder.json
    - role: normalizer
      type: normalizer
      path: preprocess/normalization_stats.json
```

## 5. Entrypoint Contract

Entrypoints are referenced by dotted paths in `manifest.yaml`. The platform must validate that the paths exist before execution.

Required entrypoints for trainable plugins:

```text
model_class
trainer_class
preprocess_function
postprocess_function
```

Required entrypoints for inference-only plugins:

```text
predict_function
preprocess_function
postprocess_function
```

Future runtime expectations:

```python
class CustomTrainer:
    def __init__(self, project_context, train_config, output_dir):
        ...

    def prepare(self):
        ...

    def train(self, emit_metric, should_stop):
        ...

    def finalize(self):
        ...
```

The plugin must not write outside `output_dir`.

## 6. Input Contract

The input contract defines what the plugin expects from the project.

Supported future input types:

```text
image_dataset
yolo_dataset
csv_feature_sequence
sequence_manifest
tabular_dataset
custom_manifest
```

Each input contract must define:

- input type
- required project files
- tensor layout
- dtype
- shape
- feature order
- label source
- train / val / test split requirements

## 7. Output Contract

The output contract defines what the plugin produces.

Supported future output types:

```text
class_probability
class_label
regression_value
sequence_regression
object_detection
instance_segmentation
semantic_segmentation
custom_dict
```

The platform must reject plugins whose output contract cannot be mapped to the selected project task.

## 8. Dependency Policy

Dependencies are high risk and must be controlled.

Rules:

1. Dependencies are declared in `requirements.txt`.
2. The platform must not auto-install dependencies in this phase.
3. A future sandbox runner may install dependencies only after explicit user approval.
4. Package installation must happen in an isolated environment, not in the app runtime environment.
5. Network access for dependency installation is disabled by default.
6. Dependency resolution results must be written to a validation report.

Allowed dependency policy values:

```text
locked
user_approved
offline_only
disabled
```

## 9. Sandbox Permission Contract

The sandbox section declares what the plugin may access.

Default permissions:

```yaml
network: false
shell: false
gpu_access: user_approved
filesystem:
  read:
    - project.dataset
    - plugin.package
  write:
    - project.training.runs.current
  denied:
    - user_home
    - system_root
    - app_binary_dir
```

The platform must treat missing sandbox permissions as denied.

High-risk permissions:

```text
network=true
shell=true
filesystem.write outside project scope
filesystem.read user_home
auto dependency install
```

High-risk permissions require explicit user approval and must be logged.

## 10. Dry-Run Validation

Dry-run validation is mandatory before a plugin can be registered as runnable.

In P1, dry-run is specified but not executed. Any dry-run-capable package must still be marked execution-disabled until a later sandbox phase exists.

Minimum checks:

```text
1. manifest.yaml exists
2. contract_version is supported
3. plugin.id is valid and unique
4. task architecture and task_family are supported
5. required entrypoint files exist
6. dependencies are declared
7. sandbox permissions are valid
8. input_contract is compatible with project
9. output_contract is compatible with project
10. sample input exists
11. one forward pass succeeds
12. output shape matches output_contract
13. required metrics can be emitted
14. required artifacts can be written to output_dir
```

Dry-run output:

```json
{
  "status": "blocked",
  "plugin_id": "custom.sequence.lstm_v1",
  "checks": [
    {
      "name": "manifest_exists",
      "passed": true
    },
    {
      "name": "sandbox_required",
      "passed": true
    },
    {
      "name": "execution_disabled_current_phase",
      "passed": false,
      "severity": "info",
      "message": "Custom plugin execution is not enabled in this build."
    }
  ],
  "warnings": [],
  "errors": []
}
```

## 10.1 P1 Validation Report

P1 produces `validation_report.json` as its primary artifact.

Recommended schema:

```json
{
  "import_id": "imp_20260630_001",
  "package_name": "custom_road_seg.zip",
  "status": "BLOCKED_EXECUTION_DISABLED",
  "manifest_valid": true,
  "execution_enabled": false,
  "checks": [
    {
      "name": "safe_zip_extraction",
      "status": "passed",
      "message": "Package extracted inside staging directory."
    },
    {
      "name": "manifest_exists",
      "status": "passed",
      "message": "model_manifest.json found."
    },
    {
      "name": "entrypoint_declared",
      "status": "passed",
      "message": "adapter.py declared but not imported or executed."
    },
    {
      "name": "dependency_policy",
      "status": "passed",
      "message": "Dependency installation disabled in P1."
    },
    {
      "name": "sandbox_permission",
      "status": "passed",
      "message": "No network, shell, or external write permission requested."
    }
  ],
  "blocked_reasons": [
    "P1 is manifest-only validation. Execution is disabled."
  ],
  "next_allowed_action": "manual_review"
}
```

Allowed check statuses:

```text
passed
warning
failed
blocked
skipped
```

The report must be user-readable and suitable for UI display.

## 11. Metrics Contract

The plugin must emit metrics as normalized records.

Recommended JSONL format:

```json
{"epoch":1,"step":10,"key":"train/loss","value":0.91,"timestamp":"2026-06-30T10:00:00"}
{"epoch":1,"step":10,"key":"val/macro_f1","value":0.72,"timestamp":"2026-06-30T10:00:10"}
```

Metric requirements:

- keys must be stable
- values must be numeric
- epoch must be integer when training is epoch-based
- timestamp must be ISO 8601
- primary metric must match `metrics_contract.primary_metric.key`

The platform must not assume CNN metrics and RNN metrics are interchangeable.

## 12. Artifact Contract

The plugin must write artifacts under the run directory only.

Expected run directory:

```text
training/runs/{run_id}/
  backend.json
  train_config.json
  metric_schema.json
  artifact_manifest.json
  run_summary.json
  metrics.jsonl
  weights/
    best.pt
    last.pt
  logs/
    plugin.log
```

The platform generates or validates:

- `backend.json`
- `metric_schema.json`
- `artifact_manifest.json`
- `run_summary.json`

The plugin may produce:

- model weights
- preprocess metadata
- labels
- normalizers
- evaluation outputs
- plugin logs

## 13. Registration States

Plugin registration states:

```text
UPLOADED
STAGED
INSPECTED
MANIFEST_VALID
MANIFEST_INVALID
BLOCKED_EXECUTION_DISABLED
READY_FOR_REVIEW
REGISTERED_DISABLED
ENABLED
REJECTED
inspected
validated_manifest
dry_run_passed
blocked_execution_disabled
blocked_dependency_policy
blocked_sandbox_policy
failed_validation
disabled
```

Current product builds should stop at:

```text
READY_FOR_REVIEW
REGISTERED_DISABLED
BLOCKED_EXECUTION_DISABLED
```

Current product builds must not reach:

```text
ENABLED
dry_run_passed
```

Recommended P1 state flow:

```text
UPLOADED
  -> STAGED
  -> INSPECTED
  -> MANIFEST_VALID
  -> BLOCKED_EXECUTION_DISABLED
  -> READY_FOR_REVIEW
  -> REGISTERED_DISABLED
```

## 13.2 Phase P1-B Permission Gate And Approval Flow

Formal phase name:

```text
Phase P1-B: Python Adapter Sandbox Dry-Run Gate
```

P1-B does not enable adapter execution by itself. It defines and records the approval flow required before any future sandbox runner may execute a Python adapter dry-run.

Core rule:

```text
approval recorded != adapter executed
approval recorded != training enabled
approval recorded != inference enabled
```

P1-B allowed behavior:

```text
1. Read the staged package source manifest.
2. Build a sandbox permission gate.
3. Detect requested permissions.
4. Create sandbox_permission_request.json.
5. Create dry_run_report.json with execution disabled.
6. Record approve / reject decision.
7. Keep adapter_imported=false and dry_run_executed=false.
```

P1-B hard non-goals:

```text
Do not import adapter.py
Do not call adapter.py
Do not compile source
Do not run infer.exe
Do not install dependencies
Do not call /train/start
Do not mark package ENABLED
Do not mark package TRAINABLE
Do not mark package INFERENCE_READY
```

Permission gate fields:

```json
{
  "runtime_kind": "python_adapter",
  "entrypoint": "adapter.py",
  "approval_required": true,
  "execution_enabled": false,
  "permissions": [
    {
      "name": "python_adapter_execution",
      "requested": true,
      "risk": "high",
      "requires_approval": true,
      "allowed_by_default": false
    }
  ],
  "policy": {
    "network_default": false,
    "shell_default": false,
    "dependency_install_default": false,
    "external_filesystem_default": false,
    "missing_permissions_are_denied": true
  }
}
```

Approval request output:

```json
{
  "status": "APPROVAL_REQUIRED",
  "approval_status": "pending",
  "execution_enabled": false,
  "adapter_imported": false,
  "dry_run_executed": false,
  "next_allowed_action": "approve_or_reject_permissions"
}
```

Approval decision output:

```json
{
  "status": "APPROVED_EXECUTION_DISABLED",
  "decision": "approve",
  "execution_enabled": false,
  "adapter_imported": false,
  "dry_run_executed": false,
  "next_allowed_action": "sandbox_runner_required"
}
```

API boundary:

```text
POST /api/projects/{project_id}/models/import/custom-package/{model_id}/dry-run/request
POST /api/projects/{project_id}/models/import/custom-package/{model_id}/dry-run/approval
```

These APIs are approval-flow APIs. They must not execute package code.

## 13.3 Phase P1-D Sandbox Dry-Run Runner Skeleton

Formal phase name:

```text
Phase P1-D: Sandbox Dry-Run Runner Skeleton
```

P1-D introduces the runner interface and mock execution contract only. It does not import, execute, compile, spawn, or install anything from the package.

Allowed behavior:

```text
1. Read sandbox_approval_decision.json.
2. Require approved status before mock runner proceeds.
3. Read source_model_manifest.json.
4. Check that runtime.entrypoint is declared.
5. Check that the entrypoint file exists under staging.
6. Check input_spec and output_spec presence.
7. Emit mock_dry_run_report.json.
8. Keep execution_enabled=false.
9. Keep adapter_imported=false.
10. Keep user_code_executed=false.
```

Hard non-goals:

```text
Do not import adapter.py
Do not call adapter methods
Do not run Python subprocesses
Do not compile C/C++
Do not run external executables
Do not install dependencies
Do not allocate GPU
Do not write outside staging
Do not mark the package ENABLED
```

Runner interface:

```python
class SandboxDryRunRunner(Protocol):
    def run(self, import_dir: Path, model: dict) -> dict:
        ...
```

Mock dry-run report:

```json
{
  "status": "MOCK_DRY_RUN_COMPLETED",
  "execution_mode": "mock",
  "execution_enabled": false,
  "adapter_imported": false,
  "dry_run_executed": false,
  "user_code_executed": false,
  "checks": [
    {"name": "approval_recorded", "status": "passed"},
    {"name": "execution_mode_mock", "status": "passed"},
    {"name": "adapter_not_imported", "status": "passed"},
    {"name": "user_code_not_executed", "status": "passed"},
    {"name": "entrypoint_file_exists", "status": "passed"}
  ],
  "next_allowed_action": "implement_real_sandbox_runner"
}
```

API boundary:

```text
POST /api/projects/{project_id}/models/import/custom-package/{model_id}/dry-run/mock
```

This API only runs the mock contract. It must not execute package code.

## 13.0.4 Phase P1-E Sandbox Dry-Run Plan Contract

P1-E creates a non-executable plan for a future sandbox runner.

Allowed:

```text
1. Read sandbox_approval_decision.json.
2. Read source_model_manifest.json.
3. Record runtime.kind and runtime.entrypoint.
4. Record input/output contract presence.
5. Record sandbox policy defaults.
6. Write sandbox_dry_run_plan.json.
7. Keep execution disabled.
```

Hard non-goals:

```text
Do not import adapter.py
Do not build a runnable command line
Do not spawn Python
Do not compile source code
Do not install dependencies
Do not grant network, shell, GPU, or external filesystem permissions
```

Plan output:

```json
{
  "status": "SANDBOX_PLAN_READY",
  "phase": "P1-E",
  "execution_enabled": false,
  "adapter_imported": false,
  "dry_run_executed": false,
  "user_code_executed": false,
  "runtime": {
    "kind": "python_adapter",
    "entrypoint": "adapter.py",
    "entrypoint_exists": true
  },
  "sandbox_policy": {
    "network_allowed": false,
    "shell_allowed": false,
    "dependency_install_allowed": false,
    "external_filesystem_allowed": false,
    "gpu_allowed": false,
    "write_scope": "staging_only",
    "timeout_seconds": 30
  }
}
```

API boundary:

```text
POST /api/projects/{project_id}/models/import/custom-package/{model_id}/dry-run/plan
```

## 13.0.5 Phase P1-F Sandbox Audit Trail

P1-F records sandbox-related events for review and troubleshooting.

Audit file:

```text
sandbox_audit_log.jsonl
```

Events:

```text
dry_run_permission_requested
dry_run_permission_approve
dry_run_permission_reject
sandbox_plan_created
sandbox_plan_blocked
mock_dry_run_contract_checked
```

Every event must preserve these safety flags:

```json
{
  "execution_enabled": false,
  "adapter_imported": false,
  "dry_run_executed": false,
  "user_code_executed": false
}
```

API boundary:

```text
GET /api/projects/{project_id}/models/import/custom-package/{model_id}/dry-run/audit
```

## 13.0.6 Phase P1-G UI Contract Actions

P1-G exposes contract-only actions in the Model Import approval panel:

```text
Build sandbox plan
Mock dry-run
```

Both actions are intentionally non-executable:

```text
Build sandbox plan -> writes sandbox_dry_run_plan.json
Mock dry-run -> writes mock_dry_run_report.json
```

The UI must continue to show:

```text
Execution Disabled
Adapter was not imported or executed.
```

## 13.0.7 Phase P2 Real Isolated Dry-Run Runner Design

P2 defines the real isolated dry-run runner policy, but still does not execute
custom package code.

Reference:

```text
docs/SANDBOX_DRY_RUN_POLICY.md
```

P2 adds a policy payload to sandbox_dry_run_plan.json:

```text
p2_isolated_runner_policy
```

This policy must keep:

```json
{
  "execution_enabled": false,
  "adapter_imported": false,
  "dry_run_executed": false,
  "user_code_executed": false
}
```

P2 is complete when the platform can describe the future process isolation
requirements without importing, spawning, or executing user adapter code.

## 13.0.8 Phase P3 Dependency Lock / Offline Environment Check

P3 inspects dependency metadata only.

Output:

```text
p3_dependency_environment_check
```

Rules:

```text
Do not install dependencies
Do not access network
Do not import adapter.py
Do not spawn Python
Require offline mode before real dry-run
Require lock file before future executable dry-run
```

## 13.0.9 Phase P4 Sandboxed Process Runner Enforcement

P4 defines the process runner enforcement contract, but still does not spawn a
process.

Output:

```text
p4_process_runner_enforcement
```

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

P4 must keep:

```json
{
  "execution_enabled": false,
  "process_spawned": false,
  "adapter_imported": false,
  "dry_run_executed": false,
  "user_code_executed": false
}
```

## 13.0.10 Phase P5 Registry Enablement Policy

P5 evaluates whether a custom package can move toward manual registry
enablement review.

P5 is still not an execution phase.

Rules:

```text
Mock dry-run is not sufficient for enablement.
REAL_DRY_RUN_PASSED is required for future enablement.
P3 dependency check must pass.
P4 process enforcement must be ready.
```

Output:

```text
registry_enablement_policy.json
```

Before a real dry-run exists, P5 must return:

```text
P5_ENABLEMENT_BLOCKED
```

## 13.0.11 Phase P6 Limited Integration Contract

P6 describes selector integration rules after P5.

P6 must not directly register a custom package into training or inference.

Output:

```text
limited_integration_contract.json
```

Before P5 passes, selector visibility must remain:

```json
{
  "training_selector": false,
  "inference_selector": false,
  "evaluation_selector": false
}
```

## 13.0.12 Phase P7 Sandbox Worker Threat Model

P7 defines the threat model for a future real sandbox worker prototype.

Reference:

```text
docs/SANDBOX_THREAT_MODEL_P7.md
```

P7 scope:

```text
assets to protect
trust boundaries
threat categories
mitigation requirements
approval gates
failure policy
future implementation acceptance gates
```

P7 hard non-goals:

```text
Do not implement the real worker
Do not execute adapter.py
Do not run subprocesses
Do not install dependencies
Do not enable training
Do not enable inference
```

Invalid package flow:

```text
UPLOADED
  -> STAGED
  -> INSPECTED
  -> MANIFEST_INVALID
  -> REJECTED
```

## 13.1 UI Labels

UI must avoid labels that imply runtime availability.

Allowed P1 labels:

```text
Inspected
Manifest Valid
Execution Disabled
Needs Review
Registered Disabled
```

Forbidden P1 labels:

```text
Ready
Active
Enabled
Trainable
Runnable
Inference Ready
```

UI should separate:

```text
Import Result
Execution Status
```

Example:

```text
Import Result: Manifest valid
Execution Status: Blocked - execution disabled in current phase
```

## 14. Security Rules

The platform must enforce these rules:

1. Never execute unknown Python during import.
2. Never auto-install requirements during import.
3. Never write plugin files into the executable directory.
4. Never allow plugin writes outside the current project or run directory.
5. Never allow shell access by default.
6. Never allow network access by default.
7. Always log high-risk permission requests.
8. Always require dry-run before runnable registration.
9. Always show user-readable validation reports.

## 15. Future Implementation Phases

Recommended sequence:

```text
Phase P1: Manifest-only custom model package validation
Phase P2: Plugin package import UI, inspection only
Phase P3: Dry-run validator in isolated process
Phase P4: Dependency lock and offline environment check
Phase P5: Sandboxed process runner
Phase P6: TrainingStateStore / Runner integration
Phase P7: metrics and artifact contract integration
Phase P8: limited custom plugin execution
```

RNNBackend, CNN-LSTM, external scripts, TensorFlow, ONNX training, and full plugin execution should not be enabled until the sandbox runner and validation pipeline are complete.
