# Changelog

All notable changes to Vision Training Studio are tracked here.

## [Unreleased]

## [0.1.3] - 2026-07-22

### Added
- Added Enter-to-send, Shift+Enter line breaks, duplicate-submit protection, and a visible searching state to Project Assistant.
- Added first-open knowledge checks plus an in-context synchronization action when the active project's knowledge base is empty.
- Added page-aware, evidence-cited next-step guidance for training, evaluation, comparison, and export questions.
- Added a shared system Downloads service with safe filenames and collision-preserving saves for evaluation artifacts.

### Changed
- Localized Project Assistant no-source, disabled-mode, execution-trace, and failure messages for Traditional Chinese sessions.
- Save CNN and RNN evaluation charts directly to the Windows Downloads folder instead of relying on WebView temporary download behavior.

### Fixed
- Prevent Project Assistant from appearing unresponsive while a project search is running.
- Prevent evaluation SVG downloads from being redirected into the application's AppData workspace.

## [0.1.2] - 2026-07-22

### Added
- Added installable and trainable image classification models: ResNet18, MobileNetV3 Large, and EfficientNet-B0.
- Added installable and trainable detection models: D-FINE Small, Faster R-CNN, and FCOS.
- Added Mask R-CNN instance segmentation plus DeepLabV3 and built-in U-Net semantic segmentation.
- Added TorchVision and Transformers D-FINE training backends with standard run artifacts.
- Added task-aware CNN augmentation for overcast light, sun suppression, depth fog, layered rain, wet surfaces, puddles, splashes, and isolated lens droplets.
- Added draggable before/after augmentation preview with Polygon/BBox overlays and geometry remapping.
- Added dynamic risk guidance for vertical flips, random crops, and geometry-label review without blocking the operation.

### Changed
- Grouped the training model selector by image classification, object detection, instance segmentation, and semantic segmentation.
- Kept unavailable optional weights visible with an installation prompt instead of hiding the model.
- Added class-folder imports and stratified splitting for image-classification projects.
- Restored the compact CNN training monitor with native-scale per-metric charts arranged in a Full HD 3-by-2 grid and updated once per completed epoch.
- Reworked augmentation controls into six aligned Full HD parameter groups and kept risky transforms disabled by default.
- Unified long-running task progress, page lifecycle caching, and completed-run restoration across CNN and RNN workflows.
- Redesigned RNN training, testing, comparison, feature/label configuration, and shared model guidance workspaces.

### Fixed
- Pass the selected model backend from the training UI so non-YOLO models no longer fall back to the YOLO backend.
- Preserve the saved Run model when the training page refreshes instead of replacing it with the generic hardware recommendation.
- Remove redundant installed-status text from trainable model options while retaining installation and task-compatibility guidance where action is required.
- Keep project task selection editable and explain visual task types with consistent Traditional Chinese and English guidance.
- Prevent stale augmentation previews from being applied after parameter or source-image changes.

## [0.1.1] - 2026-07-16

### Fixed
- Compact the live training monitor into a responsive horizontal summary instead of stacked full-width cards.
- Keep training status synchronized through WebSocket updates plus HTTP fallback polling, including completed, failed, stopped, and early-stopping outcomes.
- Record and display successful early stopping so the UI no longer leaves users waiting on a stale in-progress indicator.
- Select CUDA training from PyTorch device availability instead of requiring optional NVIDIA telemetry support.
- Restore the translated project-refresh notification after terminal training updates.

### Added
- Added durable first-run completion state under the user configuration directory, including migration from the legacy browser-only review marker.
- Added release validation evidence for the rebuilt Windows runtime, portable archive, installer, clean installation, same-path upgrade, and uninstall data retention.

### Changed
- Redesigned model preparation as a first-run-only wizard and a separate optional-resource manager that does not preselect or require recommended downloads.
- Extended the installer build script to discover per-user Inno Setup installations.
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
