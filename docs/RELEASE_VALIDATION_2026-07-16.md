# Release Validation — 2026-07-16

## Scope

Validation covers the first-run model preparation change, a rebuilt Windows runtime, portable archive, installer, isolated clean installation, and same-path upgrade behavior.

## Artifacts

| Artifact | Size (bytes) | SHA-256 |
|---|---:|---|
| `VisionTrainingStudio_Setup_0.1.0.exe` | 1,632,820,395 | `9EDF789AD7E941E1D9DBE886E31E36A4B31EB017305F7A8E1A1D663E0D2C04A0` |
| `VisionTrainingStudio_0.1.0_Windows_x64_portable.zip` | 2,847,634,347 | `ABB252A3885C69830DF1CB644BBC2FFDD6CFC63BEE1DC792D8A32728A51F752D` |
| Packaged `VisionTrainingStudio.exe` | 55,687,661 | `A14379555928797BC7820BC91869F2E7866FEA768C6468887A93D7C800339A99` |

Generated artifacts remain excluded from Git.

## Validation Results

| Check | Result | Evidence |
|---|---|---|
| Full unit/integration/static suite | PASS | 363 tests passed |
| JavaScript syntax and Python compilation | PASS | `scripts/build.bat` |
| PyInstaller warning audit | PASS | 0 blocker, 0 unclassified, 6 watch warnings |
| Installed offline smoke | PASS | OpenCV 5.0.0.93; 0 projects; 0 automatic model downloads; 0 external connections |
| Portable offline smoke | PASS | OpenCV 5.0.0.93; 0 projects; 0 automatic model downloads; 0 external connections |
| Portable ZIP integrity | PASS | 8,403 files; ZIP CRC test passed |
| Installer compilation | PASS | Inno Setup 6.7.3 |
| Isolated clean installation | PASS | Installer completed and installed EXE launched healthy |
| Clean first run | PASS | Initial setup appeared once; completion persisted across application restart |
| Same-path upgrade | PASS | Installer overwrote the isolated installation successfully |
| Legacy onboarding migration | PASS | Browser review state migrated to durable state with `outcome=migrated`; prompt stayed hidden |
| Uninstall | PASS | Application files removed; separate user data retained |

## First-run Acceptance

1. A factory-clean user-data directory reports `initial_setup_completed=false`.
2. The packaged UI displays the four-step initial setup.
3. Completing without a model download writes the durable onboarding marker.
4. Restarting the packaged application with the same user data does not reopen the prompt.
5. For upgrade simulation, the durable marker was removed while the legacy browser review state was retained.
6. After same-path installer overwrite, the UI stayed open without the prompt and recreated the durable marker as `outcome=migrated`.

## Environment Boundary

The clean and upgrade installations used isolated application and user-data directories on a Windows x64 validation host. This validates installer/runtime behavior without touching normal user projects or settings. It does not replace a final acceptance pass on a separate clean Windows VM or physical machine.
