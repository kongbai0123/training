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
