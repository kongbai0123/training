# P7 Sandbox Worker Threat Model

Status: design only

P7 defines the threat model for a future real sandbox worker prototype. It does not implement or execute the worker.

## Objective

Define what must be protected before the platform can safely import and run a custom `adapter.py` dry-run.

P7 is complete when the risks, mitigations, acceptance gates, and non-goals are documented.

## Assets To Protect

```text
project data
training runs
imported model packages
application source and executable files
user filesystem outside the project
model weights
environment variables
license files
GPU / CPU / RAM resources
network access
audit logs
```

## Trust Boundaries

```text
trusted:
  main app code
  signed application resources
  project metadata written by the app

untrusted:
  uploaded custom package zip
  adapter.py
  train.py
  preprocess.py
  postprocess.py
  src/*.py
  src/*.c / src/*.cpp
  bin/*.exe
  requirements.txt
  package model_manifest.json fields not independently verified

controlled boundary:
  staging directory
  generated sample input
  sandbox output directory
  JSON stdout/stderr report
```

## Threat Categories

| Threat | Example | Required Mitigation |
| --- | --- | --- |
| Path traversal | zip writes `../../file` | safe extraction, staging-only paths |
| Arbitrary code execution | adapter deletes files | isolated worker, approval gate, no main-process import |
| Data exfiltration | adapter uploads project data | network disabled by default |
| Secret access | reads env vars or license files | sanitized environment |
| Dependency attack | malicious package install | no auto install, lock/offline check |
| Resource abuse | infinite loop, memory burn | timeout and resource limits |
| Filesystem damage | writes outside staging | write-only output scope |
| Shell escape | `subprocess`, shell commands | shell denied by default |
| GPU abuse | long GPU job | GPU denied until explicitly supported |
| Report spoofing | fake JSON success | schema validation and audit correlation |
| Registry poisoning | marks itself enabled | app-owned policy writes only |

## Minimum Worker Architecture

Future P7 worker shape:

```text
main process
  -> validates package, approval, P3, P4
  -> creates isolated work directory
  -> writes generated sample input
  -> launches worker with sanitized environment
  -> captures stdout/stderr
  -> validates JSON result
  -> writes dry_run_report.json
  -> updates audit log
```

Worker restrictions:

```text
no inherited secrets
no network by default
no shell by default
no dependency install
no write outside sandbox output
timeout required
stdout JSON required
stderr captured
non-zero exit code is failure
invalid JSON is failure
missing output is failure
```

## Approval Gates

Before a real dry-run can execute:

```text
1. manifest valid
2. permission request created
3. user approval recorded
4. P3 dependency check passed
5. P4 enforcement contract ready
6. worker isolation available
7. output schema validator available
8. audit logging enabled
```

Approval does not mean:

```text
training enabled
inference enabled
registry enabled
unrestricted filesystem access
network access
dependency install permission
```

## Failure Policy

The main app must treat these as failed dry-runs:

```text
timeout
non-zero exit code
invalid JSON
missing required fields
adapter exception
stderr policy violation
write outside output scope
network attempt
dependency install attempt
shell attempt
resource limit exceeded
```

Failed dry-run result:

```json
{
  "status": "REAL_DRY_RUN_FAILED",
  "execution_enabled": false,
  "eligible_for_registry_enablement": false
}
```

Successful dry-run result may only become:

```text
READY_FOR_REVIEW
```

It must not automatically become:

```text
ENABLED
TRAINABLE
INFERENCE_READY
```

## P7 Non-Goals

```text
Do not implement real worker in this phase.
Do not execute adapter.py.
Do not call /train/start.
Do not add custom package to training selector.
Do not add custom package to inference selector.
Do not support C/C++ compilation.
Do not run external executables.
Do not install dependencies.
Do not allow network.
Do not allow GPU.
```

## Acceptance Gates For Future Implementation

A future implementation cannot start until all are available:

```text
worker entrypoint spec
worker JSON schema
sanitized environment builder
timeout controller
resource limit strategy
safe output directory enforcement
stdout/stderr parser
policy violation classifier
audit event writer
unit tests for failure modes
```

