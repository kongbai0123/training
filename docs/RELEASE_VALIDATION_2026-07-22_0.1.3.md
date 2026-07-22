# Release Validation - 2026-07-22 - 0.1.3

## Scope

This validation covers the project-assistant interaction improvements and the correction that saves evaluation chart exports to the Windows Downloads folder instead of application data storage.

Source implementation commit: `4fffc19 feat: improve project assistant and evaluation downloads`.

## Artifacts

| Artifact | Size (bytes) | SHA-256 |
|---|---:|---|
| `VisionTrainingStudio_Setup_0.1.3.exe` | 1,746,595,279 | `A6F32596C85C3E3E086D95905AD19AFF7AF7407AA5D9A67680E615865A69A395` |
| `VisionTrainingStudio_0.1.3_Windows_x64_portable.zip` | 3,091,177,379 | `B7BD8C9BA86E8F122665552CAF519E5A712EC64176B8512D57DE5C6B1B412D4F` |

Generated binaries remain excluded from Git.

## Validation Results

| Check | Result | Evidence |
|---|---|---|
| Full unit, integration, and static suite | PASS | 473 tests and 144 subtests passed |
| JavaScript syntax and Python compilation | PASS | Static checks completed before packaging |
| Project-assistant empty knowledge state | PASS | Empty state displayed a sync action instead of a silent response |
| Project-assistant keyboard behavior | PASS | Enter submitted; Shift+Enter retained a newline |
| Project-assistant busy state | PASS | Input and send action showed a searching state until the response completed |
| Project-assistant localization | PASS | The `zh-TW` no-source response explained that project artifacts must be synchronized |
| Project-assistant grounded response | PASS | After synchronization, the browser rendered three source cards without console errors or warnings |
| Evaluation SVG save from development runtime | PASS | File created under `C:\Users\user\Downloads` |
| Packaged installed-mode offline smoke | PASS | Version 0.1.3; OpenCV 5.0.0.93; RTX 3060 detected; zero automatic model downloads and external connections |
| Portable-mode offline smoke | PASS | Version 0.1.3; portable data path; zero automatic model downloads and external connections |
| Portable ZIP integrity | PASS | 11,391 files; 4,958,192,545 uncompressed bytes; package contract completed |
| Installer compilation | PASS | Inno Setup 6.7.3 completed successfully |
| Isolated installer execution | PASS | Silent installation completed with exit code 0 under `build/installed_validation_0.1.3` |
| Installed application health | PASS | `/api/health` healthy and `/api/version` returned 0.1.3 |
| Installed assistant response | PASS | Local-session authenticated call returned the localized no-source guidance |
| Installed evaluation download | PASS | SVG created at `C:\Users\user\Downloads\VTS_0.1.3_installed_download_acceptance_20260722_181406.svg`; no AppData path was used |

## Compatibility

- Windows 10/11 x64 packaging remains unchanged.
- Installed mode keeps projects under `%LOCALAPPDATA%/VisionTrainingStudio/projects` while user-requested downloads use the Windows Downloads known folder.
- Portable mode continues to store application data beside the executable, but explicit chart downloads still use the Windows Downloads folder.
- The assistant remains project-scoped and local-search-first; it does not silently upload project material.

## Risks / Limitations

- The default assistant is deterministic lexical retrieval, not a generative model with unrestricted reasoning.
- Answers depend on synchronized project artifacts; an empty knowledge base intentionally returns a synchronization action.
- Windows Downloads resolution uses the system known-folder registry value with the user-profile Downloads folder as a fallback.
- This validation proves packaging and installed behavior on the current Windows x64 host; clean-machine acceptance remains a separate release gate.
