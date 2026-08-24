# Vision Training Studio 0.1.12 Release Validation

## Release identity

- App version: `0.1.12`
- Runtime version: `r1`
- Channel: `stable`
- Build date: `2026.08.24`
- Supported source version: `0.1.11`

## Scope

This release replaces the sidebar RNN/CNN mode toggle with a unified feature overview. RNN and CNN are registered as independent modules and continue to use their existing project, training, evaluation, export, and history services.

## Automated validation

- Full Python suite: `524 passed`
- Update delivery and transaction suite: `28 passed`
- JavaScript syntax checks: passed
- Traditional Chinese DOM/i18n audit: 61 nodes scanned, 0 issues
- English DOM/i18n audit: 61 nodes scanned, 0 issues
- Installed offline smoke test: passed (`/health` and `/version` reported `0.1.12`, runtime `r1`)
- Signed package verification: passed
- Automatic rollback validation: passed, 16 files restored
- Interrupted-update recovery: passed, 16 files restored

## Manual UI validation

- Unified overview opens without an active project.
- RNN and CNN cards open their corresponding workspaces.
- Returning to the shared overview hides module-specific navigation.
- Existing project routing synchronizes the correct module.
- Desktop and 1024 px layouts have no horizontal overflow.

## Update artifact

- File: `VisionTrainingStudio_Update_0.1.12_runtime-r1.vtsupdate`
- Size: `209983` bytes
- Changed files: `16`
- Removed files: `0`
- SHA-256: `ba66e1a52864b6ef40a6815aeaf22ede29ffa7c3f08725fcd5971fad926db103`
- Signature: verified

The package contains only first-party application assets and version metadata. The existing `runtime-r1` executable and third-party runtime remain unchanged.
