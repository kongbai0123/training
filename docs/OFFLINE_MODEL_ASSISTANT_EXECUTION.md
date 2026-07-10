# Offline Model, LabelMe, Assistant, and OpenCV 5 Execution Ledger

## Scope

This ledger controls work on branch `codex/offline-model-assistant-release`.
Only the following objectives are in scope:

1. Hardware capability and real model installation state.
2. Explicit-consent first-run model preparation and model source management.
3. Optional managed LabelMe runtime for offline Windows use.
4. Project Assistant UX simplification and CNN/RNN-aware context.
5. OpenCV 5 compatibility validation and gated dependency update.
6. Final offline, UI, test, and packaged-build validation.

## Baseline

| Item | Value |
| --- | --- |
| Source branch | `codex/task-aware-dashboard-status` |
| Baseline commit | `bb91d5f` |
| Python | `3.11.9` |
| PyTorch | `2.5.1+cu121` |
| Ultralytics | `8.4.68` |
| OpenCV | `4.13.0` / requirement `4.13.0.92` |
| XGBoost | `3.2.0` |
| Existing portable artifact | `release_artifacts/VisionTrainingStudio_0.1.0_Windows_x64_portable.zip` |

The branch was created with pre-existing dashboard and training UI changes in the
working tree. Those changes are preserved as the execution baseline and must not
be rewritten as part of this objective.

## Acceptance Gates

- No model or component download occurs without explicit user confirmation.
- Hardware and model state are available without an active project.
- Model availability is derived from actual files and integrity metadata.
- RNN templates remain usable without downloading pretrained weights.
- Managed LabelMe can launch without system Python after component installation.
- Assistant content is scoped to the active project architecture and page.
- OpenCV 5 is adopted only after API, UI, integration, and packaging checks pass.
- No push or merge to `main` occurs before user approval.

## Issue Policy

| Class | Handling |
| --- | --- |
| Blocker | Apply the smallest fix required to pass the current phase gate. |
| Related | Record here; do not fix during the phase unless it becomes a blocker. |
| Unrelated | Record here only; never modify as part of this objective. |

## Collected Issues

| ID | Class | Area | Observation | Impact | Proposed follow-up | Status |
| --- | --- | --- | --- | --- | --- | --- |
| EXEC-001 | Related | Packaging | Existing portable ZIP is approximately 2.73 GB before managed LabelMe or optional model components. | Full offline package may become impractically large. | Compare thin installer, component cache, and full-offline package sizes in Phase 8. | Open |
| EXEC-002 | Related | i18n | The legacy `zh-TW.js` override block still contains historical mojibake entries, although the reviewed catalog and new model-preparation strings render correctly. | Untouched pages may still expose corrupted legacy strings. | Run the scoped assistant and release-page DOM audit in Phases 5, 6, and 8; do not rebuild the entire catalog during model preparation. | Open |
| EXEC-003 | Related | Packaging | The optional offline LabelMe component is 96.5 MB compressed and 238.3 MB installed. | Bundling it into the already-large main package would penalize users who do not need manual CNN annotation. | Publish it as a separate optional component artifact and keep local ZIP installation in the first-run manager. | Open |
| EXEC-004 | Related | Development environment | The shared developer Python installation contains unrelated packages with conflicting pins (`opencv-python-headless` consumers and an old `autodistill-yolov8` Ultralytics pin). | `pip check` on the shared machine cannot represent the clean application lock set. | Keep release builds isolated from global Python packages and run dependency checks inside the release environment in Phase 8. | Open |

## Phase Evidence

Evidence is appended after each phase. A phase is not complete until its tests,
runtime checks, and compatibility result are recorded here.

### Phase 0

- Branch created: `codex/offline-model-assistant-release`.
- Pre-existing dirty changes preserved without rollback.
- Baseline test command: `python -m unittest discover -s tests`.
- Baseline result: 295 tests passed.
- Static diff check: passed; only Git line-ending notices were reported.

### Phase 1

- Added project-independent `GET /api/system/capabilities`.
- Added project-independent `GET /api/models/catalog`.
- Verified local hardware detection: NVIDIA GeForce RTX 3060, 12287 MB VRAM,
  CUDA 12.1, system RAM, user-data disk, and runtime package versions.
- Built-in weight states now come from local file existence and optional SHA-256.
- RNN templates explicitly report `installation_required: false`.
- Model catalog regression: 29 tests passed.
- Full suite result after Phase 1: 301 tests passed.

### Phase 2

- Added explicit-consent first-run model preparation and a persistent Settings entry.
- The first-run screen reads only local hardware and model catalog endpoints before
  confirmation; download POST requests are emitted only by the install button.
- Added allowlisted HTTPS downloads, redirected-host validation, `.part` staging,
  SHA-256 verification, atomic replacement, progress, cancellation, retry, and
  duplicate-install protection.
- Added hardware-aware recommendation labels using CUDA, VRAM, RAM, and disk data.
- Browser smoke verified the RTX 3060 summary, 5 optional YOLO components, 8 ready
  RNN templates, skip flow, Settings reopen flow, and Traditional Chinese rendering.
- Targeted Phase 2 result: 17 tests passed.
- Full suite result after Phase 2: 309 tests and 66 subtests passed.

### Phase 3

- Added official YOLO26, YOLO11, and YOLOv8 Detection / Instance Segmentation
  families with n/s choices; retained YOLOv8m segmentation for existing projects.
- Download sizes and SHA-256 digests were verified against the official Ultralytics
  assets `v8.4.0` release manifest.
- Hardware recommendation now selects one latest compatible model per task instead
  of marking every compatible model as recommended.
- Added source contracts for custom YOLO PT/YAML, managed project best/last
  checkpoints, built-in LSTM/GRU/BiLSTM/XGBoost templates, and external PyTorch
  packages. External packages remain manifest-validation-only with code execution
  disabled.
- Browser smoke verified the default recommendation view, family filter, YOLO11
  model list, and the collapsed source summary.
- Full suite result after Phase 3: 310 tests and 66 subtests passed.

### Phase 4

- Removed the development-agent-specific LabelMe executable path.
- Added a managed LabelMe component directory under user data and made it the
  preferred launch source; a system `labelme` executable remains a compatibility
  fallback only.
- Added project-independent component status and explicit-confirmation ZIP install
  APIs with traversal, symlink, expanded-size, platform, entrypoint, and SHA-256
  validation plus atomic replacement and rollback.
- Missing LabelMe now returns a clear 503 component-required response instead of
  trying to execute `python -m labelme` through the frozen application executable.
- Added an isolated build script for a standalone manual-annotation LabelMe 4.6.0
  component and displayed component status/install entry in first-run setup.
- Built `labelme-runtime-windows-x64.zip`: 96.5 MB compressed / 238.3 MB installed.
- Verified both the build output and a clean temporary managed installation with
  `LabelMe.exe --version` exit code 0; installed status reported `offline_ready`.
- Added `pytest.ini` to prevent build-only environments from being collected as
  application tests.
- Full suite result after Phase 4: 318 tests and 66 subtests passed.

### Phase 5

- Replaced the all-at-once workbench layout with three user-facing tabs: Q&A,
  Sources, and Settings.
- Reframed the status strip around active project, page context, assistant mode,
  and source count instead of internal model/chunk implementation details.
- Q&A now contains only the question, answer, citations, and relevant page guidance.
- Source ingestion and retrieval inspection are isolated in Sources; generation and
  external-request controls are isolated in Settings.
- Internal agent traces, sandbox editing, and assistant evaluation remain available
  in code but are removed from the primary user interface.
- Browser smoke verified exclusive panel visibility for all three tabs and confirmed
  no legacy panel is displayed.
- Full suite result after Phase 5: 322 tests and 66 subtests passed.

### Phase 6

- Added deterministic project context metadata for assistant sources:
  `architecture` (`cnn` / `rnn`) and normalized `task_type`.
- Automatic artifact sync and manual project document ingestion now attach the
  active project's architecture and task metadata.
- Retrieval and chat now apply project, page scope, architecture, and task filters;
  chunks without an exact architecture/task match are excluded when those filters
  are active.
- Added source scopes for CNN dataset, LabelMe, split, augmentation, inference,
  auto-labeling and RNN sequence dataset, feature roles, windowing, and sequence test.
- Assistant page guidance now distinguishes CNN image/annotation workflows from RNN
  schema/window/task-aware workflows, including evaluation and export prompts.
- Browser smoke verified `CNN · 模型訓練`, `RNN · 總覽`, and
  `RNN · 序列視窗`; the live RNN request preserved
  `architecture=rnn`, `task_type=sequence_regression`, and `scope=windowing`.
- Temporary RNN smoke project was removed after verification.
- Targeted Phase 6 result: 30 tests and 5 subtests passed.
- Full suite result after Phase 6: 324 tests and 66 subtests passed.

### Phase 7

- Confirmed the official Windows x64 `opencv-python==5.0.0.93` wheel is available.
- Added `scripts/check_opencv_compatibility.py` to exercise all 24 OpenCV symbols
  used by the application plus image round trips, contours, transforms, encoding,
  augmentation, dataset utilities, and inference polygon conversion.
- OpenCV 4.13 baseline compatibility check passed before changing the requirement.
- Created an isolated OpenCV 5 environment instead of mutating the application
  runtime before validation.
- OpenCV 5.0.0 with NumPy 2.1.3 passed the compatibility gate and full suite.
- The locked release combination OpenCV 5.0.0 with NumPy 2.4.6 passed the same
  compatibility gate and full suite.
- Updated `requirements.txt` to `opencv-python==5.0.0.93` only after both gates passed.
- Isolated OpenCV 5 result: 325 tests and 66 subtests passed.
- Updated the source runtime to OpenCV 5.0.0 / NumPy 2.4.6; the health endpoint
  remained healthy and the capabilities endpoint reported `opencv=5.0.0.93`.
- Browser smoke verified the dashboard and active CNN project still render after the
  runtime upgrade.
- Full suite result after Phase 7: 326 tests and 66 subtests passed.
