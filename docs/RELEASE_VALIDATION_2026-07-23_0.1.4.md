# Vision Training Studio 0.1.4 release validation

Date: 2026-07-23

Branch: `codex/incremental-updater`

Runtime: `r1`

## Release role

Version 0.1.4 is the full-installer bootstrap for signed incremental updates.
Older installations must install 0.1.4 once. Later application-only releases
that keep runtime `r1` can use a small signed `.vtsupdate` package.

## Validated artifact

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `VisionTrainingStudio_Setup_0.1.4.exe` | 1,645,070,629 | `3986CA936C617FB1A6F50AC3D83173F584D94F26A1F169064EBABFBBDCFBFAEC` |

The final installer contains `VisionTrainingStudioUpdater.exe` with SHA-256
`4A241790E22925AE9496D088C337F84942EA7D2B34F6A28825641DE6490E8EBF`.

## Validation results

| Check | Result | Evidence |
| --- | --- | --- |
| Full source regression | PASS | 482 tests |
| JavaScript and Python build checks | PASS | `scripts\build.bat` |
| Packaged offline smoke | PASS | version 0.1.4, CUDA GPU, OpenCV 5, no project leakage, no automatic model download, no external connection |
| Clean uninstall of 0.1.1 | PASS | application directory removed |
| User-data preservation | PASS | 3 project directories and 5 model files remained before and after install/update |
| Clean 0.1.4 installation | PASS | installed version and health API returned 0.1.4 / r1 |
| Installed assistant and Downloads export | PASS | assistant returned localized guidance; SVG saved under the Windows Downloads directory |
| Installed updater API | PASS | status returned 0.1.4 / r1 with no active blockers |
| Offline update import | PASS | signed 0.1.5 acceptance package registered as ready |
| Installed incremental update | PASS | updater closed 0.1.4, applied two files, journal completed, and relaunched 0.1.5 |
| Payload tamper rejection | PASS | modified payload was rejected and installed hashes did not change |
| Apply-failure rollback | PASS | deliberately missing staged version file produced `rolled_back`; all three affected paths matched their original hashes |
| Interrupted-update recovery | PASS | simulated interruption after version replacement produced `rolled_back` and restored the original version |
| Final installer updater identity | PASS | installed updater hash matched the updater in the validated distribution |

The 0.1.5 package used above is an acceptance fixture, not a public release.

## Compatibility decision

- Application-only changes under the allowlisted executable, static, data,
  documentation, and version paths may use `.vtsupdate`.
- Any Python package, native library, CUDA/Torch component, embedded updater, or
  other runtime change requires a new full installer and a new runtime baseline.
- Projects, models, datasets, settings, logs, exports, licenses, and assistant
  knowledge are outside the update transaction boundary.

## Known limitations

- Version 0.1.4 itself must be distributed as the full installer because older
  versions do not contain the updater.
- The updater executable is runtime-owned in phase 1. Updating the updater
  itself requires a full installer.
- Windows code signing is not configured yet. Update packages are Ed25519
  signed, but the installer and executables should also receive Authenticode
  signatures before a broad commercial release.
