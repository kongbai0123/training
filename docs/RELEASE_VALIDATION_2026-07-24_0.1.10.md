# Vision Training Studio 0.1.10 Incremental Update Validation

Date: 2026-07-24

Runtime: `r1`
Supported source version: `0.1.9`

## Artifact

- Package: `VisionTrainingStudio_Update_0.1.10_runtime-r1.vtsupdate`
- Size: 158,112 bytes
- SHA-256: `e90a0a9d0ed3933bc63bc4cd19243f155bd5dfd0ea0425a89f612880202253fc`
- Signed manifest: verified with the bundled Ed25519 public key
- Changed files: 8
- Removed files: 0

## Validation Path

The installed baseline was created from the complete 0.1.6 installer and then
updated through the signed 0.1.7, 0.1.8, and 0.1.9 packages. The resulting
0.1.9 installation was hashed as the runtime-r1 baseline before building the
0.1.10 package.

| Check | Result |
| --- | --- |
| Source/runtime compatibility | PASS — 0.1.9 / runtime-r1 |
| Package signature and payload hashes | PASS |
| Successful transactional apply | PASS — 8/8 installed hashes matched |
| Restart and health endpoint | PASS — `healthy`, version `0.1.10` |
| Installed Model Guide page | PASS |
| Inline task menu | PASS |
| Object-detection filter | PASS — model count changed from 62 to 25 |
| Fixed filter actions | PASS — both actions visible inside the filter panel |
| Independent panel scrolling | PASS |
| Evidence before compatibility conclusion | PASS |
| Browser console warnings/errors | PASS — none |
| Automatic failure rollback | PASS — 8 files restored |
| Interrupted-update recovery | PASS — 8 files restored |
| Post-update cleanup | PASS — staging/cache reduced to zero; one rollback backup retained |

## Scope

This is an incremental front-end update. It does not replace the updater,
launcher, embedded Python/Node runtime, core dependencies, or installation
directory structure, so a full EXE or installer rebuild is not required.
