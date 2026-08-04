# Documentation Sync Plan

## Status

Refreshed for the Repository Harness Core 0.1.7 migration on 2026-08-04.
Earlier source inputs remain canonicalized and archived.

## Canonical Targets

| Area | Canonical Target | Status |
| --- | --- | --- |
| Repository workflow | `AGENTS.md`, `docs/WORKFLOW.md` | current |
| Documentation map | `docs/README.md` | current |
| Product state | `docs/product/current-state.md` | current |
| Architecture overview | `docs/architecture/overview.md` | current |
| App-ready data contract | `docs/architecture/data-contracts.md` | current |
| Storage strategy | `docs/architecture/storage-strategy.md` | current |
| System 1 ingestion | `docs/architecture/system1-ingestion.md` | current |
| System 2 retrieval | `docs/architecture/system2-retrieval.md` | target architecture; runtime not implemented |
| Decisions | `docs/decisions/` | canonical |
| Validation matrix | `docs/validation/test-matrix.md` | canonical durable proof index |

## Rule

Do not reopen archived source inputs unless explicitly doing archaeology. When
code, tests, runtime evidence, and canonical docs disagree, record the conflict
and update the owning current-state or validation document. Do not restore the
retired SQLite Harness control plane as a second source of truth.
