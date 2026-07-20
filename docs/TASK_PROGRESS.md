# Unified Task Progress

Vision Training Studio uses one progress contract for loading, importing, synchronization, model installation, training, evaluation, inference, and export.

## Front-end contract

- Use `apiFetch` or `apiFetchBlob` for normal requests. Requests that remain active for 500 ms automatically receive an inline progress row and a global progress HUD.
- Use `apiUpload` for every file transfer. It reports browser transfer bytes as a real percentage, then switches to indeterminate server processing.
- Use `beginTask` only for a multi-request workflow that needs an overall progress value. Do not emit `progress:*` events directly from feature pages.
- Use `followServerTask(jobId)` for long-running server work. It consumes the shared WebSocket endpoint and falls back to status polling.
- Set `suppressProgress: true` only for internal polling that is already represented by a visible task.

The shared controller owns button busy state, `aria-busy`, the page-level progress row, global HUD updates, and terminal success or failure state.

## Back-end contract

Submit long-running work through `task_job_manager` and return:

```json
{
  "job_id": "task_import_...",
  "task": { "status": "queued", "phase": "queued" }
}
```

Clients observe jobs through:

- `GET /api/tasks/{job_id}`
- `POST /api/tasks/{job_id}/cancel`
- `WS /api/tasks/{job_id}/ws`

Handlers report a stable `phase`, user-safe `message`, `progress`, `indeterminate`, and optional `current` / `total`. Use real units whenever the total is known; use indeterminate progress while a library operation cannot expose a reliable total.

Standard phases include `queued`, `preparing`, `validating`, `scanning`, `extracting`, `decoding`, `converting`, `loading_model`, `inferencing`, `applying`, `synchronizing`, `writing`, `completed`, `failed`, and `cancelled`.

## Current long-task coverage

- Local folder, video, ZIP, image, and annotation import workflows
- LabelMe and project-assistant synchronization
- Dataset split, quality check, and augmentation
- Auto-labeling
- Image and sequence inference
- Multi-model output comparison
- Model installation
- CNN and RNN training monitoring
- CNN and RNN model export

New long operations must use the same contract instead of adding page-specific spinners or timers.
