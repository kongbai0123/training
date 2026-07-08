# Vision Training Studio UI Design System

Status: practical hardening baseline for Phase 6.

## Purpose

This document defines the UI contract used by the local desktop web shell. The goal is not a cosmetic redesign; it is to keep critical workflows consistent, testable, and safe to operate.

## Structure

- `static/style.css` is the import shell only.
- `static/styles/tokens.css` owns color, radius, shadow, and text tokens.
- `static/styles/components.css` owns reusable buttons, badges, panels, cards, tables, forms, and toast behavior.
- `static/styles/pages/*.css` owns page-specific layout only.

## Operational Patterns

- Structured API errors must surface `code`, `message`, `suggestion`, `retryable`, and `status` through `VtsApiError`.
- Dirty forms must warn through the dashboard alert stack and `beforeunload`.
- Stale project data must be visible after mutating local API calls until the project is refreshed.
- CNN guided onboarding must route users to the real project, dataset, annotation, split, training, and compare pages.
- Deployment decisions must separate recommendation, blockers, reasons, risks, and next actions.

## UI Smoke Contract

Static smoke tests use `data-ui-smoke` markers for user-critical surfaces:

- `cnn-guided-wizard`
- `dirty-form-alert`
- `stale-resource-alert`
- `deployment-decision-card`

These markers are not styling hooks. They are stable test hooks for Phase 6 UI smoke validation.

## Deployment Decision

The Model Compare Center must show a Deployment Decision card whenever a comparison result exists. The card must identify the recommended run, confidence level, blockers, reasons, risks, and next actions before export.

## Accessibility And Layout Rules

- Buttons must use existing `.btn` classes and include icons where an icon already exists in the shell.
- Repeated operational cards use `--radius` and must fit desktop and tablet widths.
- Text must wrap inside cards and buttons; do not rely on viewport-scaled font sizes.
- Warnings and blockers use `.status-guard`, `.badge-warning`, or `.badge-danger`.
