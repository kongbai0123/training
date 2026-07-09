# Project Assistant UX Plan

Status: Active product direction  
Branch: `codex/rag-workbench-ux-plan`  
Product boundary: Vision Training Studio remains a general model training platform.

## Product Decision

Vision Training Studio is not a RAG product and not a document Q&A system. Its core workflow remains:

1. Import trainable data.
2. Configure schema, labels, and task type.
3. Select trainable models.
4. Run controlled training.
5. Review artifacts, metrics, diagnostics, and comparisons.
6. Export deployment files.

Project Assistant is an auxiliary layer for understanding the active project. It must not become a training mode, a first-level sidebar item, or a separate workbench that competes with CNN/RNN workflows.

## Assistant Role

Project Assistant can help users understand:

- dataset schema
- training config
- training runs
- metrics and diagnostics
- evaluation reports
- model comparison reports
- export contracts
- error logs
- project notes and docs

It must only read active-project evidence unless the user explicitly imports scoped project notes. Unscoped assistant requests must not see other project documents.

## Navigation Placement

Allowed placement:

- header assistant shortcut
- workspace context panel
- Project Summary
- Evaluation
- Model Compare
- Export
- History / Reports

Disallowed placement:

- primary sidebar as a training workflow peer
- CNN/RNN mode selector peer
- default first screen
- standalone document Q&A product entry

## LLM Mode Decision

Core training, evaluation, comparison, and export must not depend on LLM or GGUF availability.

Supported assistant modes:

- `disabled`: no assistant generation.
- `local_search_only`: default; local project search and cited sources, no LLM required.
- `local_gguf`: optional future local LLM backend.
- `cloud_api`: optional future cloud LLM backend after explicit user configuration.

Deterministic metrics and platform rules remain the source of truth for model selection. The assistant can explain evidence, summarize reports, and propose next diagnostic steps, but it must not override metric-based evaluation.

## Current Implementation

Implemented components:

- Backend service: `src/project_assistant_service.py`
- Primary API routes: `src/api/routes/project_assistant.py`
- Primary service alias: `src/project_assistant.py`
- Frontend page: `static/pages/project_assistant.js`
- Frontend implementation: `static/pages/project_assistant_impl.js`
- Page CSS: `static/styles/pages/project_assistant.css`
- Header/context entry: `static/index.html`
- Context-aware assistant panel: `static/core/right_panel.js`
- i18n catalogs: `static/state/i18n/en.js`, `static/state/i18n/zh-TW.js`
- Contract tests: `tests/test_project_assistant_contract.py`
- Static page tests: `tests/test_project_assistant_page_static.py`

Legacy compatibility components:

- `src/rag_workbench.py`
- `src/api/routes/rag_workbench.py`
- `static/pages/rag_workbench.js`
- `/api/rag-workbench/*`
- `?page=rag-workbench` route alias

These legacy names are compatibility shims only. User-facing copy should say Project Assistant, Training Diagnostic Assistant, Project Q&A, Source Search, or Project Knowledge.

## Implemented Behavior

- Project Assistant is not present as a primary sidebar page.
- Header and context panel can open the assistant.
- Project Summary, Evaluation, Model Compare, Export, and History show context-aware assistant suggestions.
- Context panel can sync active project artifacts without opening a separate assistant page.
- Active-project artifact sync indexes:
  - project summary
  - dataset and schema
  - training runs and metrics
  - exports and inference contracts
- Repeated sync replaces only auto-indexed documents for the same project.
- Manual project notes remain untouched.
- Unscoped knowledge-base and chat requests return no active-project documents.
- Scoped requests only retrieve documents matching the active project id.
- Assistant mode defaults to local search only.
- Optional GGUF / cloud modes are settings, not core workflow dependencies.

## Validation Evidence

Recent validation on this branch:

- `scripts\build.bat`
- `scripts\test.bat`
- DOM audit for `project-assistant` and `rnn:export` in `zh-TW`
- API contract tests for project-scoped knowledge base, chat, upload, SSE, and artifact sync
- Static tests proving no primary sidebar `rag-workbench` page and no visible RAG copy in the Project Assistant page

## Guardrails

- Do not add RAG as a first-level navigation item.
- Do not make LLM or GGUF mandatory for training, evaluation, comparison, inference, or export.
- Do not let UI text, button labels, traces, or rendered source cards leak into conversation state.
- Do not expose raw chain-of-thought.
- Do not read documents across projects unless an explicit project scope allows it.
- Do not claim OS-level sandboxing for the assistant artifact preview.
- Do not let assistant recommendations override deterministic metrics.

## Remaining Work

Recommended next slices:

1. Add page-specific assistant prompts for RNN schema, sequence training, model comparison, export, and error history.
2. Add project report summarization templates that do not require an LLM.
3. Add optional LLM generation only behind explicit assistant mode settings.
4. Extend DOM audit pages for Evaluation, Compare, Export, History, and Project Assistant after each UI copy change.

## Completion Criteria

This feature is aligned when current-state evidence proves:

- Vision Training Studio remains a general training platform.
- Assistant entry points are secondary and contextual.
- Active-project scoping is enforced in API and UI flows.
- Local search works without LLM/GGUF.
- LLM/GGUF modes are optional.
- Evaluation and comparison remain deterministic.
- Visible UI copy no longer presents this as RAG Workbench.
