# Custom Model Packages

Custom model support is package-based. A single `.py`, `.cpp`, or `.c` file is not treated as a trainable model because the application cannot infer entrypoints, data contracts, metrics, artifacts, or security permissions from a loose source file.

Phase P1-A supports **ZIP import + static validation only**:

- reads the ZIP central directory;
- checks for path traversal, symlinks, executable payloads, file count, and uncompressed size;
- parses `manifest.yaml`, `manifest.yml`, `model_manifest.yaml`, `model_manifest.yml`, `model_manifest.json`, or `manifest.json`;
- validates model identity, entrypoints, input/output contract, metrics contract, and security policy;
- stores the package and validation report under the active project;
- never imports package code, never extracts into the runtime, and never starts training.

## Package layout

```text
custom_model_package.zip
├─ manifest.yaml
├─ model.py
├─ train.py
├─ predict.py
├─ dataset.py
├─ preprocess.py
├─ postprocess.py
├─ requirements.txt
└─ README.md
```

C/C++ source files may be present as source assets, but compiled binaries and shell scripts are blocked in this phase.

## Manifest contract

```yaml
model:
  name: Custom Road Model
  architecture: cnn
  task_type: segmentation
  framework: pytorch

entrypoints:
  trainer: train.train
  predictor: predict.predict

input:
  type: image
  shape: [3, 640, 640]

output:
  type: segmentation_mask
  classes: [asphalt, cement, gravel]

metrics:
  required: [train/loss, val/loss]
  optional: [precision, recall, f1, miou]

security:
  allow_network: false
  allow_shell: false
  allow_write: project_only
```

Entrypoints use `module.function` or `module:function` notation. The validator checks that the referenced Python module file exists in the ZIP, but it does not import the module.

## Status semantics

```text
valid_manifest_execution_disabled
```

The package is understandable by the system, but it is not trainable yet.

```text
invalid_manifest
```

The ZIP could be read, but required contract fields are missing or malformed.

```text
blocked
```

The package requests a disallowed security capability or contains unsafe ZIP entries or executable payloads.

## Next implementation phases

1. Sandbox plan and approval record: records user intent but still does not execute code.
2. Mock dry-run: builds synthetic input/output and metrics previews from the manifest only.
3. Real sandbox dry-run: isolated process/container, dependency allow-list, no network by default, project-only artifact output.
4. Training enablement: package can enter the training selector only after dry-run, metrics, artifact, and UI progress contracts pass.
