# Vision Training Studio 0.2.0 full-installer risk validation

Validation date: 2026-09-01
Target: Windows x64 full offline GPU installer

## Decision

The incompatible `0.2.0 runtime-r1` incremental package is not a valid recovery or release asset. Version 0.2.0 must be delivered through the full installer rebuilt from one consistent dependency environment.

## Artifact

| Artifact | Bytes | SHA-256 | Authenticode |
| --- | ---: | --- | --- |
| `VisionTrainingStudio_Setup_0.2.0.exe` | 1,560,344,143 | `d9b4d1ec9813641dee71c13a1137fc31d274f27b2b37342a86da904c61a31d14` | Internal-QA unsigned; formal publication blocked until a trusted certificate is supplied |

The installer is 85,156,508 bytes (5.18%) smaller than the previous build and remains below the enforced 2 GiB ceiling. CUDA/PyTorch stays bundled to preserve offline GPU operation.

## Validation results

| Check | Result |
| --- | --- |
| Transaction rollback journal | PASS; state `rolled_back`, zero rollback errors |
| Rolled-back 0.1.12 startup | PASS |
| Consistent dependency environment | PASS; `pip check` reported no broken requirements |
| Packaged 0.2.0 installed smoke | PASS |
| Runtime | PASS; PyTorch 2.5.1+cu121 and OpenCV 5.0.0.93 |
| Factory project isolation | PASS; zero projects exposed |
| Automatic model downloads | PASS; zero downloads |
| External connections | PASS; zero connections |
| Isolated test uninstall | PASS; test installation removed |
| Formal unsigned release guard | PASS; unsigned installer rejected |

## Publication gate

The repository supports signing from a trusted certificate in the Windows certificate store through `VTS_SIGN_CERT_SHA1`. A build without that value is explicitly internal-QA only. The GitHub release helper performs strict Authenticode verification and cannot publish an unsigned full installer.
