# Project Assistant UX Plan

Status: Repositioned from standalone RAG Workbench to project-scoped assistant  
Branch: `codex/rag-workbench-ux-plan`  
Source: product decision to keep Vision Training Studio centered on general model training

## Objective

Keep Vision Training Studio centered on a general training workflow. RAG-style retrieval is retained only as an assistant capability for explaining active-project data, runs, reports, exports, and logs.

This is not a standalone RAG product or document Q&A system. It must not become a first-level training mode or primary navigation item.

The plan is intentionally organized by major execution phases only. Do not split this into small item-by-item feature fixes such as Phase 1.1 or Phase 1.2 during planning. Each phase should be implemented as a coherent product slice with its own validation evidence.

## Current Repository Fit

This repository is currently a Vision Training Studio focused on CNN/RNN training workflows, dataset management, model evaluation, auto-labeling, model comparison, export, run artifacts, and packaging.

Evidence from the current tree:

- UI shell and workspace context exist in `static/index.html`, `static/core/right_panel.js`, and `static/styles/layout.css`.
- Experiment artifacts and run registry concepts exist in `src/training/artifact_manifest.py`, `src/training/run_registry.py`, and `src/training/export_service.py`.
- Sandbox policy concepts exist for custom model packages in `docs/SANDBOX_DRY_RUN_POLICY.md`, `docs/SANDBOX_THREAT_MODEL_P7.md`, and `src/model_system/`.
- i18n audit tooling exists in `scripts/i18n_dom_audit.mjs` and `docs/I18N_AUDIT.md`.
- A project-scoped assistant can reuse local search, source citation, run registry, and report concepts without changing the core CNN/RNN training workflow.

Decision: treat this as Project Assistant / Training Diagnostic Assistant. It is a helper for the active project, not a direct peer of CNN/RNN training.

## Product Principles

- Keep the visual direction; the problem is mostly information architecture and workflow clarity.
- Make project evidence, retrieval sources, assistant traces, and report references clear without hiding deterministic metrics.
- Separate display state from model input state. UI text, buttons, tool logs, and source snippets must not leak into the next model prompt.
- Prefer evidence-oriented UX. Users should know whether the answer came from RAG, which sources were used, whether indexing is complete, and what the agent actually executed.
- Build toward a project assistant that supports the training platform, not a separate RAG workbench product.

## Phase 0: Discovery And Scope Lock

Purpose: keep the assistant subordinate to the general training platform.

Required work:

- Inventory existing pages, APIs, CSS, JS state patterns, and runtime services.
- Confirm which existing concepts can be reused: workspace context, artifact registry, export patterns, i18n audit, sandbox policy.
- Confirm which concepts are missing: project-scoped ingestion, optional embeddings, retrieval profiles, source citations, assistant run registry, answer evaluation.
- Produce an implementation boundary that avoids breaking CNN/RNN workflows and avoids adding RAG as a primary product mode.

Acceptance evidence:

- This document or a follow-up architecture document names reusable modules and missing modules.
- The assistant scope is not conflated with the existing training platform.
- The assistant does not appear as a first-level sidebar item.
- No core training behavior is changed during this phase.

## Phase 1: Assistant Information Architecture

Purpose: make the feature read as project assistance inside the training platform rather than a general chat UI or standalone workbench.

Required work:

- Remove first-level RAG navigation from the left sidebar.
- Define a project-level assistant entry in the header and context panel.
- Expose assistant context only where it helps: Evaluation, Model Compare, Export, History, and Reports.
- Define a compact assistant status that exposes local-search mode, project document count, chunk count, and index state.
- Define when the contextual assistant card is useful and when it should stay hidden.

Acceptance evidence:

- A user sees the assistant as an optional project helper, not as a training mode.
- The left sidebar remains focused on training workflows.
- The page shell is still responsive and does not regress existing navigation.

## Phase 2: Knowledge Base Workflow

Purpose: make document ingestion understandable and trustworthy.

Required work:

- Redesign the upload entry point around document-to-index readiness.
- Show ingestion stages: upload, parse, chunk, embed, index.
- Show document count, chunk count, index state, failed files, and actionable failure reasons.
- Provide document list, chunk preview, re-index, remove document, and clear index actions.

Acceptance evidence:

- Users can tell whether uploaded files are ready for RAG questions.
- Ingestion failures identify the failed stage and next repair action.
- The UI avoids implying that upload completion equals retrieval readiness.

## Phase 3: State Model Separation

Purpose: prevent UI and agent process text from polluting model context.

Required work:

- Define separate state models for conversation, UI display, agent run, RAG sources, and artifacts.
- Stop building prompt history from DOM `innerText`.
- Send only clean user/assistant content plus explicit metadata to model APIs.
- Keep sources, buttons, process logs, validation blocks, and artifacts out of prompt history unless explicitly selected.

Acceptance evidence:

- Button labels, source cards, agent logs, and UI hints do not appear in future model requests.
- State can be inspected independently from rendered DOM.
- Regression tests or smoke tests prove message history cleanliness.

## Phase 4: RAG Sources And Answer Trust

Purpose: make RAG answers auditable.

Required work:

- Add API/SSE support for a `sources` event or equivalent structured source payload.
- Render cited documents with file name, page/section, score, and excerpt.
- Allow source cards to open a chunk preview.
- Show a clear warning or state when an answer has no sources.
- Visually distinguish RAG answers from normal chat answers.

Acceptance evidence:

- A RAG answer displays the documents and chunks used to generate it.
- Source rendering is structured, not embedded as plain text in the answer.
- Source data is not mixed into the next model prompt unless intentionally referenced.

## Phase 5: Agent Execution Flow

Purpose: replace raw model thought displays with professional execution tracing.

Required work:

- Remove or hide raw thought surfaces from the user-facing workflow.
- Render agent process as steps: planning, retrieval, tool execution, validation, final answer.
- Give each step a state: pending, running, done, failed.
- Preserve tool events and validation results as trace data.
- Show failure reasons in user-readable language.

Acceptance evidence:

- Users see an auditable execution flow, not raw chain-of-thought text.
- Failed tool or validation steps are diagnosable without exposing internal reasoning.
- Agent runs can be reopened or inspected after completion.

## Phase 6: Retrieval Workbench

Purpose: let users debug retrieval quality without relying only on final chat answers.

Required work:

- Add a retrieval test surface for query input.
- Show top-k chunks, raw score, rerank score, metadata, and source location.
- Support retrieval profile comparison.
- Support metadata filters.
- Allow marking bad or irrelevant retrieval results for later evaluation.

Acceptance evidence:

- Users can distinguish retrieval failure from generation failure.
- Retrieval profiles can be compared using the same query.
- Retrieved chunks are visible before answer generation.

## Phase 7: Sandbox And Artifacts Workspace

Purpose: make generated artifacts behave like a real multi-file workspace.

Required work:

- Define a virtual project file model.
- Preview must compose `index.html`, CSS, and JS instead of previewing only the current HTML file.
- Update preview when any relevant file changes.
- Show file tree, active file, preview, and export/download actions.
- Keep sandbox execution boundaries explicit.

Acceptance evidence:

- A multi-file artifact project previews correctly.
- Editing CSS or JS changes the preview without requiring users to manually rebuild unrelated state.
- Sandbox limitations are visible and do not imply full OS-level isolation unless implemented.

## Phase 8: Evaluation And Run Registry

Purpose: make RAG quality measurable and reviewable.

Required work:

- Create a RAG run registry for query, answer, sources, model, retrieval config, latency, and result metadata.
- Support golden-set evaluation.
- Track citation coverage, source hit rate, retrieval quality, latency, failure type, and answer review status.
- Export evaluation reports.
- Allow replaying past runs.

Acceptance evidence:

- RAG quality can be compared across model/retrieval configurations.
- Runs are inspectable after the session ends.
- Reports include source evidence and evaluation metadata.

## Phase 9: Visual System And CSS Maintainability

Purpose: keep the existing professional visual direction while making future changes safer.

Required work:

- Preserve the current visual identity unless a product decision changes it.
- Consolidate design tokens for surfaces, text, borders, focus, code, process blocks, and tool blocks.
- Remove duplicate selectors and hard-coded light/dark violations.
- Add responsive breakpoints for sidebar, modals, sandbox, and workbench panels.
- Split or reorganize CSS into clear semantic sections.

Acceptance evidence:

- Light and dark modes remain coherent.
- Small screens do not overflow on primary workbench flows.
- CSS changes have predictable ownership and fewer override collisions.

## Phase 10: i18n And Copy Consistency

Purpose: make the workbench credible in both visible and hidden UI text.

Required work:

- Put visible text, placeholders, titles, aria labels, tooltips, and alt text into i18n catalogs.
- Standardize terminology for RAG, retrieval, knowledge base, source, citation, agent run, artifact, and sandbox.
- Run DOM audit against primary workbench pages.
- Review page-level copy manually after automated checks.

Acceptance evidence:

- Switching language updates visible text and hidden interaction text.
- Domain terminology is consistent.
- DOM audit output is either clean or has documented acceptable exceptions.

## Phase 11: Validation, Commit Split, And Delivery

Purpose: ensure changes are reliable, reviewable, and reversible.

Required work:

- Run unit and integration tests for new contracts.
- Run UI smoke tests for major assistant flows.
- Run DOM i18n audit.
- Run screenshot checks for desktop and narrow layouts.
- Split commits by product slice: information architecture, state model, project knowledge, sources, assistant flow, source search, artifact drafts, evaluation, CSS, i18n.
- Avoid mixing unrelated training-platform changes into assistant commits.

Acceptance evidence:

- Each phase has test or inspection evidence tied to its acceptance criteria.
- Commits are focused and can be reverted independently.
- Delivery notes identify incomplete or intentionally deferred assistant capabilities.

## Implementation Guardrails

- Do not claim the Project Assistant is complete until all phases have current-state evidence.
- Do not reuse the word sandbox to imply full OS isolation unless that is implemented and verified.
- Do not surface raw chain-of-thought as a product feature.
- Do not let rendered UI text become model conversation history.
- Do not bury project knowledge state behind settings or secondary modals.
- Do not mix this work with CNN/RNN training UI fixes unless a shared shell change is explicitly required.

## LLM Mode Decision

The assistant must not be a dependency of the training platform.

Modes:

- `disabled`: no assistant generation.
- `local_search_only`: default mode; local project search with cited sources, no GGUF or external LLM required.
- `local_gguf`: optional future local LLM backend.
- `cloud_api`: optional future external LLM backend, only after explicit user configuration.

The deterministic evaluation engine remains responsible for metrics and best-model decisions. The assistant can explain and summarize evidence but must not override model evaluation results.

## Recommended First Execution Slice

The branch now contains an offline-first MVP that implements the full major-phase surface without depending on external embedding providers or hosted LLM APIs.

Implemented evidence:

- Backend service: `src/rag_workbench.py`
- Project Assistant service alias: `src/project_assistant.py`
- API route module: `src/api/routes/rag_workbench.py`
- App route registration: `app.py`
- Frontend page alias: `static/pages/project_assistant.js`
- Frontend implementation: `static/pages/rag_workbench.js`
- Workbench shell: `static/index.html`
- Page CSS: `static/styles/pages/rag_workbench.css`
- i18n entries: `static/state/i18n/en.js`, `static/state/i18n/zh-TW.js`
- Contract tests: `tests/test_rag_workbench_contract.py`
- Static page tests: `tests/test_rag_workbench_page_static.py`

Verification evidence:

- `scripts\test.bat` passes: 272 tests.
- `scripts\build.bat` passes.
- Browser DOM smoke confirms `?page=project-assistant` renders cleanly in `zh-TW` with no visible text, placeholder, title, aria-label, or tooltip issues.
- API smoke confirms assistant settings can switch to `disabled`, block chat with `assistant_disabled`, then reset to `local_search_only`.
- Browser interaction smoke confirms document ingestion, retrieval results, grounded answer sources, and agent steps render in the UI.

Implemented phase coverage:

- Phase 0: repository fit documented; implementation stays isolated from CNN/RNN project flows.
- Phase 1: Project Assistant page with header/context entry points, no primary sidebar navigation entry, and compatibility alias for legacy `rag-workbench` URLs.
- Phase 2: text document ingestion with upload / parse / chunk / embed / index stages, document list, re-index, and clear KB.
- Phase 3: frontend keeps `conversationState`; backend sanitizes accepted roles and ignores UI-only state.
- Phase 4: chat returns structured sources separately from answer text and renders source cards.
- Phase 5: agent execution is rendered as parse / retrieve / validate / final steps; raw thought is not surfaced.
- Phase 6: retrieval workbench supports query, profile selection, scores, ranked chunks, and bad retrieval marks.
- Phase 7: sandbox artifact workspace composes HTML, CSS, and JS into preview and exports a ZIP artifact.
- Phase 8: evaluation registry summarizes run count, citation coverage, source hit rate, latency, and failure types.
- Phase 9: RAG CSS is isolated under the page CSS module with responsive breakpoints.
- Phase 10: new visible text, placeholders, title, and aria labels are represented in i18n catalogs.
- Phase 11: route, service, page, i18n, CSS, build, unittest, API smoke, and browser smoke checks were executed.

Known MVP limits:

- Retrieval uses local lexical token scoring, not a production vector database.
- Answer generation is deterministic and extractive, not connected to a hosted or local LLM.
- Sandbox preview is browser iframe isolation only; it is explicitly not OS-level isolation.
- File ingestion currently accepts text payloads through the API/UI. Binary PDF parsing is intentionally not claimed.
