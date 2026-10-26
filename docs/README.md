# Project Documentation Map

This directory is the shared documentation source of truth for humans and agents.

## Project Docs

| Path | Content | Main reader |
| --- | --- | --- |
| `docs/product/` | Product behavior, competition rules, acceptance criteria, API contracts, and current state. `official/` holds organizer source material. | humans and agents |
| `docs/architecture/` | System 1 / System 2 structure, data contracts, and storage. System 1: `system1-target.md` (pipeline), `system1-ingestion.md` (Phase00), `data-contracts.md` (tables, IDs, runtime contract). | humans and agents |
| `docs/archive/` | Superseded documents kept for history (old System 1 spec, throughput, Notebook 01, scene grouping, Vietnamese data-contract explainer, old roadmap). Not authoritative. | humans |
| `docs/decisions/` | Numbered lasting product and architecture decisions. | humans and agents |
| `docs/roadmap/` | Remaining steps after the System 1 pipeline simplification (`README.md`). | humans |
| `docs/plans/active/` | Durable execution plans currently in progress. | agents |
| `docs/plans/completed/` | Validated execution history worth retaining. | agents |
| `docs/validation/` | Behavior-to-proof matrix and doc/code conflict records. | humans and agents |
| `docs/agents/` | Project rules for coding agents: `GUIDE.md` (coding, gates, handoff) and `plain-prose.md` (writing style). Loaded through `AGENTS.md`. | agents |

Component guides live next to the code: `system1/README.md`,
`system1/notebooks/README.md` (System 1 notebook runbook), `mvp-app/README.md`,
`deploy/kaggle/README.md`, and `system1/research/`.

## Harness-Managed Files

These files come from Repository Harness Core and are maintained by
`scripts/bin/harness update`. Edit only project-specific sections.

| Path | Purpose |
| --- | --- |
| `AGENTS.md` | Agent entrypoint. The `HARNESS` block is managed; the header (rules, repository map, authority map, verification) is project-owned. |
| `CLAUDE.md` | Imports `AGENTS.md` for Claude Code, which does not read `AGENTS.md` on its own. |
| `docs/WORKFLOW.md` | Agent work shapes, judgment, validation, and completion rules. |
| `docs/patterns/encoding-invariants.md` | Turn accepted rules into native mechanical validation. |
| `docs/templates/` | Optional decision, plan, runbook, and Harness-improvement structures. |
| `docs/*/README.md` | Folder introductions for plans, decisions, and product. |
| `.agents/skills/` | `$onboard-repository`, `$audit-onboarding-proposal`, `$encode-invariant`, and `$improve-harness`; each runs only when explicitly invoked. |
| `.harness-core/` | Upstream base copy used for three-way updates. Do not edit. |

Harness maintenance:

- `scripts/bin/harness status`
- `scripts/bin/harness doctor`
- `scripts/bin/harness update --dry-run`
- `scripts/bin/harness update`

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

## Freshness Rule

If code and docs disagree, record the conflict and classify it as `confirmed`,
`partial`, `unknown`, or `not implemented`. Use
`docs/validation/doc-conflicts.md` when the drift must remain visible.
