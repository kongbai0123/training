# Known Issues

This document tracks accepted product and engineering gaps for the current beta line.

## P0

- No open P0 issue after the current hardening pass.

## P1

- `app.py` remains a large API composition file. Extract route groups incrementally into `src/api/routes/*`.
- Training runtime state still has compatibility paths across `TrainingStateStore`, trainer stop flags, backend stop flags, and run artifacts.
- Frontend state and layout files are large and need gradual component/state boundaries.

## P2

- GitHub Actions runs the non-GPU pytest, compile, CSS-token, and generated API-contract gates. Formatter, full type checking, coverage, axe, and visual regression are not yet all enforced in CI.
- Release validation is script-driven and requires manual execution.
- Only the core project, task, training status/start, and readiness contracts are currently targeted for generated frontend API types; remaining routes are intentionally untyped.
- Interrupted jobs are visible and retryable after restart, but are not automatically resumed.

## Security

- Local Trusted Mode must remain disabled by default.
- Custom model package sandboxing has policy and dry-run concepts, but should not be described as full OS-level isolation.
- Commercial license signing should use an asymmetric signature scheme before paid external distribution.

## Release Rule

Do not mark a release as production-ready unless all release validation commands pass:

```bat
scripts\test.bat
scripts\build.bat
scripts\package.bat
scripts\smoke_dist.bat
```
