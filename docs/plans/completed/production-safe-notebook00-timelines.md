# Execution Plan: Production-Safe Notebook 00 Timelines And Sync

Date: 2026-08-11

## Status

Completed

## Outcome

Notebook 00B/00C create and validate one canonical metadata JSON and one exact
decoded frame timeline per video while raw media is already in bounded scratch,
then build and reconcile an exact Phase00 release without accepting stale local
or remote artifacts.

## Context

- `docs/architecture/data-contracts.md` requires decoded frame timelines for
  exact frame/time mapping while preserving canonical metadata schema 1.0.
- `docs/architecture/system1-ingestion.md` requires production Phase01 to fail
  rather than silently fall back when decoded timelines are missing.
- `docs/stories/system1/SYS1-HR-001-production-safe-notebook00/` is the current
  Notebook 00 behavior and validation authority.
- The current worktree already contains the prefix-specific progress filename
  fix; this work preserves and extends it.

## Scope

In scope:

- Stream/local raw upload timeline generation, manifesting, resume, and strict
  production failure.
- Canonical HF ingest timeline materialization without re-downloading videos.
- Exact Notebook 00B/00C gates, meaningful workflow switches, clean notebook
  state, and strict Notebook 01 timeline checks.
- Deterministic batch replacement and resumable/reconciling Phase00 HF sync.
- Tests and canonical documentation updates.

Out of scope:

- Implementing production TransNet, ASR, Gemini, SigLIP, or BEiT3 providers.
- Deleting any Git branch, raw prefix, other release, or remote path outside the
  configured `<release_id>/phase00_ingestion/` prefix.
- Publishing Git changes unless separately requested.

## Approach

1. Extend raw artifacts with per-video timeline Parquet generated in existing
   bounded scratch and uploaded beside canonical video/metadata.
2. Teach HF ingest to consume and validate those compact timeline artifacts;
   use explicit required/optional/disabled policy for compatibility.
3. Make notebook gates exact and switches truthful, then enforce required
   timelines at the Notebook 01 production boundary.
4. Make batch assignment replace stale derived files and make Phase00 sync use
   hashes, batched retries, and scoped stale deletion.
5. Update docs and prove behavior with focused, full-suite, and notebook checks.

## Risks And Recovery

- Existing raw prefixes lack timeline fields. Required resume re-extracts only
  affected source pairs and uploads missing timelines without replacing existing
  video/metadata bytes.
- A failed multi-commit Phase00 reconciliation may leave an incomplete prefix.
  The completion manifest is written last; rerunning recomputes local hashes and
  reconciles the exact prefix.
- Scoped deletion is restricted to the configured Phase00 prefix and covered by
  tests that prove unrelated paths remain untouched.
- If live HF validation cannot run without credentials/quota, local integration
  proof remains authoritative and the missing live rehearsal is reported.

## Progress

- [x] Audit current notebooks, package behavior, docs, tests, and dirty changes.
- [x] Add raw decoded timeline contract and strict resume behavior.
- [x] Materialize required timelines during canonical HF ingest.
- [x] Correct Notebook 00B/00C and Notebook 01 gates.
- [x] Replace stale batch artifacts and reconcile Phase00 HF sync.
- [x] Update tests and documentation.
- [x] Run focused and repository-wide validation.

## Decisions

- 2026-08-11: Generate decoded timelines while videos are already in stream
  scratch to avoid a second roughly 74 GB HF download.
- 2026-08-11: Production timeline failure fails the pair/run; degraded mapping
  remains explicit compatibility/debug behavior only.
- 2026-08-11: Rerunning one release ID reconciles and deletes stale files only
  inside its exact Phase00 remote prefix.
- 2026-08-11: Canonical metadata JSON remains schema 1.0; timeline additions are
  additive raw manifest/inventory/report fields.
- 2026-08-11: ADR 0017 records raw-upload timeline ownership. A prior Phase00
  completion marker is invalidated in the first changed sync commit and restored
  only after all batches succeed.

## Validation

- Focused proof: canonical metadata/timeline, raw stream resume, HF ingest,
  batch replacement, and Phase00 reconciliation tests.
- Integration proof: required-policy raw upload to Phase00 with no raw video
  download, plus retry/resume and stale-file reconciliation simulations.
- Repository-required checks: notebook JSON/cell compilation, Ruff, `git diff
  --check`, and the complete System 1 test suite.

## Result

Implemented the production timeline path across raw upload, canonical HF ingest,
Phase00 reconciliation/restore, Notebook 00B/00C, and the Notebook 01 boundary.
Raw upload now creates metadata plus a validated decoded timeline in the same
bounded scratch lifecycle; required resume backfills missing timelines without
re-uploading existing video/metadata. HF ingest transfers only compact timeline
Parquet files and removes stale local timelines.

Batch assignment replaces stale batch files. Phase00 sync uses SHA-256/size
skips, bounded commits/retries, exact-prefix deletion, and a completion marker
that is invalidated before changed operations and written last. Restore requires
and validates that marker plus every downloaded file before replacing the local
snapshot, then removes stale materialized batch/timeline artifacts.

Validation on 2026-08-11:

- `uv run pytest -q`: 182 passed.
- Focused timeline/raw/HF/sync/notebook suite: 95 passed.
- Ruff `E9,F,I`: passed for all changed Python files.
- Notebook 00B/00C/01 JSON, cleared output state, and code-cell compilation:
  passed.
- CLI help for stream upload, ingest, process-batch, and Phase00 sync: passed.
- `git diff --check`: passed.

Live HF/Drive full-dataset execution was not run locally because it requires the
operator credentials, source dataset, and quota. That rehearsal remains the
next operational validation, not an implementation gap.
