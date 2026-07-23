# `.vtsupdate` Package Specification — Format 1

## Container

The package is a ZIP64 archive with the `.vtsupdate` extension.

```text
manifest.json
manifest.sig
release_notes/zh-TW.md
release_notes/en.md
payload/<installation-relative paths>
```

`manifest.sig` is a base64 Ed25519 signature over the UTF-8 canonical JSON representation of `manifest.json` using sorted keys and compact separators.

## Allowed application paths

- `VisionTrainingStudio.exe`
- `_internal/version.json`
- `_internal/static/**`
- `_internal/data/**`
- `_internal/docs/**`

Other `_internal` content is runtime-owned and requires a full installer when changed.

## Validation invariants

- Paths are forward-slash relative paths.
- Absolute paths, drive prefixes, backslashes, empty segments, and `..` are rejected.
- Symbolic links and case-insensitive duplicate archive members are rejected.
- Every payload file is declared exactly once.
- Undeclared files are rejected.
- Each file size and SHA-256 must match.
- The package may contain at most 20,000 files and 1 GiB uncompressed content.
- The signed key ID must match the embedded public key.
- The source version and runtime must be compatible before staging.

## Private-key policy

The default release private-key location is:

```text
%LOCALAPPDATA%\VisionTrainingStudio\release_keys\update_private_key.pem
```

It must be backed up securely and never committed, uploaded, logged, or included in an installer.
