# Execution Plan: Migrate To Repository Harness Core 0.1.7

Date: 2026-08-04

## Status

Active

## Outcome

Adopt Repository Harness Core 0.1.7 as the repository workflow, reconcile
canonical documentation with current code and proof, and retire the legacy
SQLite Harness control plane without changing product behavior.

## Context

- `AGENTS.md` and `docs/WORKFLOW.md` define the new workflow.
- `docs/README.md` maps current repository truth.
- `docs/validation/test-matrix.md` is the Markdown proof index that must survive
  removal of `harness.db`.
- Baseline commit: `06b639003cc5dcbd46bcada7d124e26fecda5f0d`.
- Installer SHA-256: `b0199c9a665864b61443cf0ded003a5b5c5b3003fe328a2144c7d0e27c259ea9`.

## Scope

In scope:

- Install and validate Harness Core 0.1.7 with merge semantics.
- Run the read-only onboarding proposal and an independent proposal audit.
- Reconcile product, architecture, planning, story, onboarding, and validation docs.
- Remove the legacy Harness policy docs, CLI, schemas, database, and tracked backups.

Out of scope:

- Product code or public contract changes.
- Repairing `00_master_ingestion_and_assignment.ipynb`.
- Reading or changing `system1/research/`.
- Rewriting Git history to purge historical backup blobs.

## Approach

1. Install the checksum-verified core with `--merge --refresh-agent-shim`.
2. Commit the isolated bootstrap at a clean revision.
3. Run `$onboard-repository` read-only and audit its authenticated proposal in
   an independent session before applying documentation hunks.
4. Reconcile repository truth using current code, tests, and accepted decisions.
5. Retire the old control plane only after Markdown truth and Harness health pass.
6. Validate, record the result, and move this plan to `docs/plans/completed/`.

## Risks And Recovery

- Managed-file conflicts: stop with `.harness-core/update/` intact and resolve
  through `harness update --continue`; do not overwrite consumer content.
- Lost durable status: compare current `harness.db` stories, decisions, and
  backlog with Markdown before deleting it; Git retains the historical database.
- Documentation overclaim: classify claims from accepted docs, observed code,
  and tests; record unresolved conflicts rather than inventing policy.
- Behavioral regression: compare post-migration tests with the pinned baseline.
- Rollback: revert migration commits in reverse order. The pre-migration commit
  and installer-created local backup remain recovery sources during validation.

## Progress

- [x] Captured a clean Git and System 1 test baseline.
- [x] Dry-ran and installed pinned Harness Core 0.1.7.
- [x] Passed initial `harness status` and `harness doctor`.
- [ ] Commit the isolated Harness bootstrap.
- [ ] Run and independently audit the read-only onboarding proposal.
- [ ] Apply approved documentation reconciliation.
- [ ] Retire legacy Harness artifacts and tracked backups.
- [ ] Run final validation and complete the plan.

## Decisions

- 2026-08-04: Use a full cutover; do not retain the SQLite compatibility layer.
- 2026-08-04: Remove and ignore tracked `.harness-backup/` content; rely on Git
  history rather than keeping duplicate backups in the active tree.
- 2026-08-04: Keep the legacy Notebook 00 failure outside migration scope.
- 2026-08-04: Require a two-stage exact-hunk approval gate for onboarding edits.

## Validation

- Focused proof: `scripts/bin/harness status`, `scripts/bin/harness doctor`, and
  `scripts/bin/harness update --dry-run`.
- Integration proof: authenticated onboarding proposal plus independent audit.
- Repository-required checks: `git diff --check`, documentation path/reference
  checks, and the complete System 1 pytest baseline comparison.

## Result

Pending implementation and final validation.
