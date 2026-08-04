# Execution Plan: Migrate To Repository Harness Core 0.1.7

Date: 2026-08-04

## Status

Completed

## Outcome

Adopt Repository Harness Core 0.1.7 as the repository workflow, reconcile
canonical documentation with current code and proof, and retire the legacy
SQLite Harness control plane without changing product behavior.

## Context

- `AGENTS.md` and `docs/WORKFLOW.md` define the new workflow.
- `docs/README.md` maps current repository truth.
- `docs/validation/test-matrix.md` is the durable Markdown proof index.
- Baseline commit: `06b639003cc5dcbd46bcada7d124e26fecda5f0d`.
- Harness bootstrap commit: `589b5a85465f8f374f7630c95fbb663f6374074b`.
- Installer SHA-256: `b0199c9a665864b61443cf0ded003a5b5c5b3003fe328a2144c7d0e27c259ea9`.

## Scope

Completed:

- Installed and validated Harness Core 0.1.7 with merge semantics.
- Audited the repository and reconciled active workflow, product-state,
  architecture, onboarding, story, and validation documentation.
- Removed legacy Harness policy docs, CLI, schemas, SQLite database, and tracked
  backups.
- Preserved historical recovery through Git without rewriting history.

Excluded:

- Product code or public contract changes.
- Repairing `00_master_ingestion_and_assignment.ipynb`.
- Reading or changing `system1/research/`.

## Approach And Decisions

1. Installed the checksum-verified core with `--merge --refresh-agent-shim`.
2. Committed the isolated bootstrap at a clean revision.
3. Ran the read-only onboarding proposal and independent patch-admissibility
   audits. The audits correctly rejected wording that claimed retirement before
   legacy files were actually removed.
4. Reconciled Markdown truth from current code, tests, accepted decisions, and
   the legacy database inventory.
5. Removed the old control plane and backups, then validated the final state.

Decisions retained from the active plan:

- Full cutover; no SQLite compatibility layer remains installed.
- `.harness-backup/` content is removed and ignored; Git history is the recovery
  source.
- The legacy Notebook 00 failure remains outside migration scope.
- `system1/research/` remains outside inspection and modification scope.

## Progress

- [x] Captured a clean Git and System 1 test baseline.
- [x] Dry-ran and installed pinned Harness Core 0.1.7.
- [x] Passed initial `harness status` and `harness doctor`.
- [x] Committed the isolated Harness bootstrap.
- [x] Ran authenticated onboarding proposal audits.
- [x] Reconciled active documentation with current repository truth.
- [x] Retired legacy Harness artifacts and tracked backups.
- [x] Ran final validation and completed the plan.

## Validation

- `scripts/bin/harness status`: current, installed and target version `0.1.7`,
  three intentional project-modified managed docs, zero missing files.
- `scripts/bin/harness doctor`: all checks passed.
- `scripts/bin/harness update --dry-run`: passed and preserved all managed files.
- `git diff --check`: passed.
- Active legacy-reference scan: no references remain to `docs/harness`,
  `scripts/bin/harness-cli`, or `scripts/schema` outside excluded/generated
  Harness internals.
- `uv run pytest`: 155 collected; 154 passed and one known baseline failure in
  `test_notebooks_are_operator_ready_thin_orchestration_shells` because the
  excluded legacy `00_master_ingestion_and_assignment.ipynb` filename is not in
  the accepted 00A/00B/00C set.
- `uv run ruff check`: unavailable because `ruff` is not installed in the
  existing environment; no dependency installation was needed for this
  documentation/control-plane migration.

## Result

Repository Harness Core 0.1.7 is now the active workflow. Markdown documents,
code, tests, and Git history are the durable sources of truth. The legacy
SQLite/Rust control plane and tracked backup copies have been removed. Product
behavior and the excluded notebook WIP were not changed.
