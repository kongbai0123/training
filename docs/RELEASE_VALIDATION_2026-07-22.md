# Release Validation — 2026-07-22

## Scope

Validation covers Vision Training Studio 0.1.2, including the expanded CNN/RNN workflows, task-aware model catalog, unified progress behavior, restored epoch-based training metrics, project task editing, and the redesigned CNN augmentation workspace.

## Artifacts

| Artifact | Size (bytes) | SHA-256 |
|---|---:|---|
| `VisionTrainingStudio_Setup_0.1.2.exe` | 1,632,850,857 | `A3E96A7DDDD8E95C744EDEEB7CF202BF55A44DE5F212C9ABB48D9F88C724033F` |
| `VisionTrainingStudio_0.1.2_Windows_x64_portable.zip` | 2,847,931,756 | `E0E4E3160BCA55919159B3BF5246D52D098D4DA41EE452CFEFBD9566D88FC318` |
| Packaged `VisionTrainingStudio.exe` | 55,795,302 | `B342D76D36B754A670923129089CBC0E0FEC73B66FA695E43E51B3DDAE055C0E` |

Generated artifacts remain excluded from Git.

## Validation Results

| Check | Result | Evidence |
|---|---|---|
| Full unit/integration/static suite | PASS | 445 tests passed |
| Augmentation and geometry suite | PASS | 18 tests passed, including Polygon/BBox remapping and draggable comparison preview |
| JavaScript syntax and Python compilation | PASS | `scripts/build.bat` |
| PyInstaller warning audit | PASS | 0 blockers, 0 unclassified warnings, 6 optional watch warnings |
| Packaged installed-mode offline smoke | PASS | Version 0.1.2; OpenCV 5.0.0.93; RTX 3060 detected; 0 automatic model downloads; 0 external connections |
| Portable-mode offline smoke | PASS | Version 0.1.2; OpenCV 5.0.0.93; 0 projects; 0 automatic model downloads; 0 external connections |
| Portable ZIP integrity | PASS | Factory-clean contract, required members, and ZIP CRC validated during packaging |
| Installer compilation | PASS | Inno Setup 6 |
| Isolated installer execution | PASS | Silent install completed with exit code 0 |
| Installed application health | PASS | `/api/health` healthy and `/api/version` returned 0.1.2 |
| User-data separation | PASS | Installed app resolved projects under `%LOCALAPPDATA%/VisionTrainingStudio/projects` |
| User visual acceptance of installed UI | PENDING | Installer is retained for user review before GitHub push |

## Augmentation Risk Controls

- Vertical flip and random crop remain off or zero by default because they are not appropriate for every dataset.
- Enabling vertical flip or random crop shows a non-blocking review warning.
- Rotation, scale, perspective, flip, and crop remap Polygon/BBox annotations.
- Any parameter or source-image change invalidates the previous preview; users must regenerate and inspect the preview before applying to the Train split.
- Val/Test data and original images remain unchanged.

## Environment Boundary

The installer was installed into an isolated workspace directory and started without the development Python or Node.js entrypoints. The validation proves packaged startup, versioning, hardware discovery, and user-data separation on the current Windows x64 host. Final visual acceptance is intentionally left to the user before the repository is pushed to GitHub.
