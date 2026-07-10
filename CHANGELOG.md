# Changelog

All notable changes to Vision Training Studio are tracked here.

## [Unreleased]

### Changed
- Reworked the repository landing page around Windows EXE delivery, real UI screenshots, task-aware CNN/RNN workflows, privacy boundaries, and concise user-first documentation.
- Replaced the shared generic training map with separate CNN image and RNN sequence workflow guides plus a neutral no-project preview.
- Documented packaged Auto-Labeling layout validation in `docs/CLEAN_MACHINE_VALIDATION.md`, including the packaged runtime command, viewport, CSS cache key, and stacked workbench assertions.

## [0.1.0] - 2026-06-24

### Added
- Local-first Vision Training Studio beta baseline.
- CNN / YOLO, RNN / Sequence, and XGBoost workflow foundations.
- FastAPI backend, static frontend, local launcher, packaging scripts, diagnostics, and release artifacts.

### Changed
- Productization baseline defines source/runtime data boundaries and release validation scripts.

### Known Limitations
- API routes are still concentrated in `app.py` and need incremental APIRouter extraction.
- Training runtime state still has compatibility bridges around legacy trainer state.
- CI, formatter, type check, and visual regression gates are not yet enforced.
