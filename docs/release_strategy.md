# Vision Training Studio Release Strategy

This document defines how Vision Training Studio should be updated at each product stage.

## Decision

Use the update mechanism that matches the product stage:

| Stage | Update method | Audience | Package |
| --- | --- | --- | --- |
| Development | Git branch / source zip | Engineers, agent review | Source code |
| Internal QA | PyInstaller onedir zip | Internal testers | `dist/VisionTrainingStudio/` |
| Commercial release | Windows installer | Customers | `VisionTrainingStudio_Setup_x.y.z.exe` |
| Post-release | Built-in updater / signed patch system | Customers | Managed update package |

Do not send patch zip files to general commercial users.

## Zip Types

### Source Zip

Purpose:

- Code review
- Agent handoff
- Engineering validation

Contents:

- Source files
- `static/`
- `src/`
- `app.py`
- Packaging scripts
- Documentation

Not included:

- `dist/`
- `build/`
- customer projects
- model weights unless explicitly required

### Onedir Zip

Purpose:

- Internal QA for the packaged executable
- Testing the desktop shell and bundled runtime

Contents:

- Full `dist/VisionTrainingStudio/` directory
- `VisionTrainingStudio.exe`
- `_internal/`

Rule:

- Keep the whole directory intact. The `.exe` alone is not enough.

### Patch Zip

Purpose:

- Emergency internal hotfix only
- Engineering-assisted recovery

Contents:

- Minimal changed files
- `patch_manifest.json`

Rule:

- Do not use patch zip as the normal commercial update path.
- Do not ask non-technical customers to manually overwrite Program Files.

## Version Channels

Use clear version semantics:

| Version | Meaning |
| --- | --- |
| `0.1.0-dev` | FastAPI + Web UI development baseline |
| `0.1.1-dev` | Dashboard / right panel UI redesign |
| `0.1.2-dev` | Auto-Labeling UI redesign |
| `0.2.0-alpha` | PyInstaller onedir internal QA |
| `0.2.1-alpha` | License, diagnostics, launcher hardening |
| `0.3.0-beta` | Windows installer + clean Windows smoke test |
| `1.0.0` | Commercial Local Edition release |

## Dashboard Change Policy

Dashboard UI work should not automatically trigger commercial packaging.

Recommended workflow:

1. Modify source files:
   - `static/pages/dashboard.js`
   - `static/app.js`
   - `static/style.css`
   - `static/state.js`
   - `static/index.html` only when needed
2. Run local dev validation.
3. Commit source changes.
4. Push the branch or create a source zip for review.
5. Rebuild PyInstaller only when preparing internal QA.
6. Rebuild installer only when preparing a formal release.

## Formal Installer Artifacts

Every commercial installer release should include:

- `version.json`
- `release_notes.md`
- `build_manifest.json`
- `checksum.txt`
- `license_inventory.md`
- `THIRD_PARTY_LICENSES.md`

Example `build_manifest.json`:

```json
{
  "version": "0.3.0-beta",
  "build_time": "2026-06-24T12:00:00+08:00",
  "channel": "beta",
  "commit": "abc123",
  "package_type": "installer",
  "data_migration_required": false
}
```

## Installer Update Rules

Installer updates may overwrite program files:

```text
C:\Program Files\VisionTrainingStudio\
```

Installer updates must preserve user data:

```text
C:\Users\<user>\AppData\Local\VisionTrainingStudio\
```

Always preserve:

- `projects/`
- `models/`
- `licenses/`
- `logs/`
- `config/`
- `diagnostics/`

`cache/` may be cleaned only when the release explicitly states it is safe.

## Current Practical Rule

For the current development stage:

```text
Dashboard changes -> source edit -> local validation -> commit -> push/source zip.
```

For commercial delivery:

```text
stable source -> PyInstaller onedir -> installer -> clean Windows smoke test -> release.
```
