# RAG Workbench UX Plan

Status: planning specification  
Branch: `codex/rag-workbench-ux-plan`  
Source: user UX assessment for a Local RAG + Agent + Sandbox workbench

## Objective

Move the proposed product direction from a polished chat interface toward a mature RAG Workbench.

The plan is intentionally organized by major execution phases only. Do not split this into small item-by-item feature fixes such as Phase 1.1 or Phase 1.2 during planning. Each phase should be implemented as a coherent product slice with its own validation evidence.

## Current Repository Fit

This repository is currently a Vision Training Studio focused on CNN/RNN training workflows, dataset management, model evaluation, auto-labeling, model comparison, export, run artifacts, and packaging.

Evidence from the current tree:

- UI shell and workspace context exist in `static/index.html`, `static/core/right_panel.js`, and `static/styles/layout.css`.
- Experiment artifacts and run registry concepts exist in `src/training/artifact_manifest.py`, `src/training/run_registry.py`, and `src/training/export_service.py`.
- Sandbox policy concepts exist for custom model packages in `docs/SANDBOX_DRY_RUN_POLICY.md`, `docs/SANDBOX_THREAT_MODEL_P7.md`, and `src/model_system/`.
- i18n audit tooling exists in `scripts/i18n_dom_audit.mjs` and `docs/I18N_AUDIT.md`.
- A real RAG knowledge base, retrieval workbench, citation source event stream, and RAG answer provenance workflow do not currently exist as first-class product flows.

Decision: treat this as a new RAG Workbench product/module plan, not as a direct cosmetic patch to the existing CNN/RNN training platform.

## Product Principles

- Keep the visual direction; the problem is mostly information architecture and workflow clarity.
- Make knowledge base state, retrieval evidence, answer sources, agent execution, and sandbox artifacts first-class.
- Separate display state from model input state. UI text, buttons, tool logs, and source snippets must not leak into the next model prompt.
- Prefer evidence-oriented UX. Users should know whether the answer came from RAG, which sources were used, whether indexing is complete, and what the agent actually executed.
- Build toward a workbench, not just a chat surface.

## Phase 0: Discovery And Scope Lock

Purpose: determine whether the RAG Workbench is a new module in this repo, a separate product, or a future workspace type that shares shell infrastructure.

Required work:

- Inventory existing pages, APIs, CSS, JS state patterns, and runtime services.
- Confirm which existing concepts can be reused: workspace context, artifact registry, export patterns, i18n audit, sandbox policy.
- Confirm which concepts are missing: knowledge base ingestion, embeddings, retrieval profiles, source citations, RAG run registry, answer evaluation.
- Produce an implementation boundary that avoids breaking CNN/RNN workflows.

Acceptance evidence:

- This document or a follow-up architecture document names reusable modules and missing modules.
- The RAG Workbench scope is not conflated with the existing training platform.
- No core training behavior is changed during this phase.

## Phase 1: Workbench Information Architecture

Purpose: make the interface read as a professional workbench rather than a general chat UI.

Required work:

- Define primary navigation: Chat, Knowledge Base, Retrieval, Agent Runs, Sandbox, Evaluation, Settings.
- Define a status header or workspace strip that exposes model state, RAG mode, knowledge base count, chunk count, index state, and current workspace/session.
- Reorder sidebar priority so knowledge base and current mode are visible above history.
- Define when a contextual inspector is useful and when it should collapse.

Acceptance evidence:

- A user can immediately see whether the model is available, RAG is enabled, files are indexed, and the current session is RAG-backed.
- Knowledge base management is a primary workflow, not a hidden secondary action.
- The page shell is still responsive and does not regress existing navigation if integrated into this repo.

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
- Run UI smoke tests for major workbench flows.
- Run DOM i18n audit.
- Run screenshot checks for desktop and narrow layouts.
- Split commits by product slice: information architecture, state model, knowledge base, sources, agent flow, retrieval workbench, sandbox, evaluation, CSS, i18n.
- Avoid mixing unrelated training-platform changes into RAG commits.

Acceptance evidence:

- Each phase has test or inspection evidence tied to its acceptance criteria.
- Commits are focused and can be reverted independently.
- Delivery notes identify incomplete or intentionally deferred RAG capabilities.

## Implementation Guardrails

- Do not claim the RAG Workbench is complete until all phases have current-state evidence.
- Do not reuse the word sandbox to imply full OS isolation unless that is implemented and verified.
- Do not surface raw chain-of-thought as a product feature.
- Do not let rendered UI text become model conversation history.
- Do not bury knowledge base state behind settings or secondary modals.
- Do not mix this work with CNN/RNN training UI fixes unless a shared shell change is explicitly required.

## Recommended First Execution Slice

Start with Phase 0 and Phase 1 only.

Expected deliverables:

- Architecture note naming shared shell pieces and missing RAG modules.
- Workbench navigation and status model.
- Static UI shell or mock page if implementation begins.
- No changes to CNN/RNN training behavior.

