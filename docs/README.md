# Project Documentation Map

This directory is the shared documentation source of truth for humans and agents.

## Canonical Areas

- `docs/product/`: product behavior, vocabulary, and current-state reporting.
- `docs/architecture/`: technical structure, data contracts, storage, and runtime boundaries.
- `docs/planning/`: roadmap and implementation phases.
- `docs/plans/active/`: durable work currently in progress.
- `docs/plans/completed/`: validated execution history worth retaining.
- `docs/stories/`: accepted work packets and backlog.
- `docs/decisions/`: durable product and architecture decisions.
- `docs/validation/`: behavior-to-proof matrix and validation reports.
- `docs/onboarding/`: brownfield inventories, sync records, and conflicts.
- `docs/archived/`: historical material only.

## Reading Paths

For product orientation:

1. `README.md`
2. `docs/product/current-state.md`
3. the relevant product, architecture, decision, and validation documents

For repository changes:

1. `AGENTS.md`
2. `docs/WORKFLOW.md`
3. the active execution plan, when one exists
4. only the product, design, code, tests, and validation material relevant to the task

## Harness Operations

Repository Harness Core is managed through `scripts/bin/harness`:

- `scripts/bin/harness status`
- `scripts/bin/harness doctor`
- `scripts/bin/harness update --dry-run`
- `scripts/bin/harness update`

The retired SQLite control plane is not part of the repository workflow.

## Freshness Rule

If code and docs disagree, record the conflict and classify it as `confirmed`,
`partial`, `unknown`, or `not implemented`. Use
`docs/onboarding/doc-conflicts.md` when the drift must remain visible.
