# Vision Training Studio Update Architecture

## Decision

Vision Training Studio uses two independent versions:

- `app_version` changes for UI, API, launcher, and application logic.
- `runtime_version` changes only when the packaged Python, Torch, CUDA, OpenCV, or other binary runtime changes.

An application update may replace only explicitly allow-listed application files. Any runtime change requires the full installer.

## Release topology

1. Feature branches merge into `main`.
2. A temporary `release/vX.Y.Z` branch stabilizes the candidate.
3. The validated commit receives an immutable `vX.Y.Z` tag.
4. A GitHub Release draft receives the signed `.vtsupdate`, checksums, notes, and full installer when required.
5. Assets are verified before the release is published.

Branches are not binary distribution channels. Published release assets are immutable versioned delivery artifacts.

## User-data boundary

The updater must never modify the following user-data roots:

- projects
- models
- logs
- config
- licenses
- cache
- tmp
- components
- exports
- runs
- project_assistant

Downloads, staging, journals, and backups live below the per-user update directory and remain separate from project data.

## Trust boundary

Every update is:

1. downloaded over HTTPS or imported locally;
2. checked against the declared package size;
3. verified with SHA-256 per payload file;
4. verified with an Ed25519 manifest signature;
5. checked for product, version, runtime, package-format, and path compatibility;
6. staged before any installed file is replaced.

The private signing key is never stored in the repository or application. Only the public verification key is packaged.

## Bootstrap

Version 0.1.3 does not contain an updater. Version 0.1.4 is the one-time full installer that introduces the update framework. Version 0.1.5 is the first end-to-end small-update acceptance candidate.
