# Vision Training Studio 0.1.11 Incremental Update Validation

Date: 2026-07-24

Runtime: `r1`
Supported source version: `0.1.10`

## Artifact

- Package: `VisionTrainingStudio_Update_0.1.11_runtime-r1.vtsupdate`
- Size: 88,214,216 bytes
- SHA-256: `564827d95d46cc8f3019a931a2cd7d95f4e3dbea0e5d7441cb8ff2d60b142973`
- Signed manifest: verified with the bundled Ed25519 public key
- Changed files: 12
- Removed files: 0

## Validation

| Check | Result |
| --- | --- |
| Full Python unit and integration suite | PASS — 501 tests |
| JavaScript and Python build checks | PASS |
| LabelMe cleanup unit tests | PASS — 4 tests |
| Split layout and bilingual static tests | PASS — 5 tests |
| Chinese LabelMe/Split DOM audit | PASS — 178 items, 0 issues |
| English LabelMe/Split DOM audit | PASS — 178 items, 0 issues |
| Browser batch selection | PASS — selected 2 of 3 items |
| Browser batch cleanup | PASS — queue changed from 3 to 1 |
| Report synchronization | PASS — total, YOLO TXT, and failed counts changed from 3 to 1 |
| Atomic invalid-batch protection | PASS |
| Split 2×2 alignment | PASS — right panel equals both left rows plus gap |
| Class distribution inner scrolling | PASS — disabled; client and scroll heights match |
| Browser console warnings/errors | PASS — none |
| Package signature and payload hashes | PASS — 12/12 files |
| Transactional apply and restart | PASS — health and version APIs returned 0.1.11 / runtime-r1 |
| Installed GPU/runtime discovery | PASS — RTX 3060, Torch 2.5.1+cu121 |
| Automatic rollback | PASS — 12 files restored |
| Interrupted-update recovery | PASS — 12 files restored |
| Post-update cleanup | PASS — staging/cache reduced to zero; one rollback backup retained |

## Scope

This update changes application code and first-party web assets while preserving
the updater, launcher structure, embedded runtime version, core dependencies,
and installation layout. It is delivered as a compatible `runtime-r1`
incremental update rather than a new full installer.
