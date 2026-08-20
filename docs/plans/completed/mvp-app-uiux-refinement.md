# Execution Plan: MVP App UI/UX Refinement

Date: 2026-08-19

## Status

Completed

## Outcome

Make semantic search easier to control and review: explicit optional Vietnamese
translation, Top K 100 by default and 200 maximum, in-result refinement, ten
keyframes per page, and one non-duplicated selected-keyframe view.

## Context

- `mvp-app/app.py`: current Gradio layout, callbacks, pagination, and details.
- `mvp-app/translation.py`: current language detection and translation flow.
- `mvp-app/db.py`: semantic search, pre-search filters, and result hydration.
- `mvp-app/tests/`: executable behavior and API/UI contracts.

## Scope

In scope:

- Incremental changes to existing search, translation, UI, and tests.
- Backward-compatible legacy search API plus a boolean-translation V2 endpoint.
- Refinement only within the current semantic Top K result set.

Out of scope:

- Global metadata search or metadata-only retrieval.
- Database, FAISS, release artifact, or embedding changes.
- Bounding-box rendering or a replacement UI architecture.

## Approach

Extend the existing classes and callbacks with small helpers and additional
Gradio state. Preserve the current semantic-search pipeline and pre-search
filters, then apply lightweight in-memory refinement before the existing
pagination and selection flow.

## Risks And Recovery

- Gradio endpoint compatibility: retain `/search_keyframes` and add V2 through
  a thin wrapper over shared logic.
- Gallery selection drift after filtering: page over explicit page-row state.
- Responsive CSS regressions: scope selectors to the keyframe Gallery.
- Recovery: revert this plan's focused patches; no data migration is involved.

## Progress

- [x] Inspect current implementation, runtime behavior, and test coverage.
- [x] Extend translation, Top K, and search-result hydration.
- [x] Add in-result refinement and revised pagination/UI state.
- [x] Update defaults, docs, and tests.
- [x] Run focused, full, lint, and runtime validation.

## Decisions

- 2026-08-19: Translation is enabled by default but can be bypassed explicitly.
- 2026-08-19: Top K defaults to 100 and is capped at 200.
- 2026-08-19: Refinement is limited to current semantic results; no global
  metadata lookup is added.
- 2026-08-19: Gallery preview is disabled; one original selected image remains,
  without bounding boxes.
- 2026-08-19: Prefer focused additions to current code over rewrites.
- 2026-08-19: The Gallery uses a fixed 320 px two-row viewport so all ten
  desktop thumbnails remain visible without an internal vertical scrollbar.
- 2026-08-19: In-result text search is grouped inside the refinement accordion.
- 2026-08-19: The V2 translation checkbox is authoritative; when enabled it
  runs the vi-en model directly instead of relying on unreliable language
  detection for short Vietnamese queries.

## Validation

- Focused proof: 24 focused translation, search, refinement, pagination, and UI
  tests passed initially; the follow-up Gallery, accordion, and forced short
  query translation checks pass in the expanded focused suite.
- Integration or end-to-end proof: local app started on port 7899; real V2 API
  calls verified direct Vietnamese, translated Vietnamese, Top K 200, and 20
  pages of ten results.
- Repository-required checks: full MVP suite passed with 40 tests; Ruff passed
  for all changed behavior and test files; `git diff --check` passed. Full-tree
  Ruff still reports seven pre-existing issues outside this change's scope.

## Result

Implemented the requested incremental UI/UX refinement without changing the
database, FAISS index, release artifacts, or global metadata-search behavior.
The legacy endpoint remains available and the current UI uses the boolean
translation V2 endpoint. No unresolved product risk remains; the only known
repository limitation is the disclosed pre-existing full-tree Ruff baseline.
