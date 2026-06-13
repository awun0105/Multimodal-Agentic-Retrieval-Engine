# Current State

## Status

Canonical state-of-project snapshot as of 2026-06-13.

## Implemented In Docs And Matrix

| Area | State | Evidence |
| --- | --- | --- |
| Product framing as one Web UI plus Query Sessions | confirmed | `README.md`, `docs/architecture/overview.md`, `docs/product/query-workflows.md` |
| App-ready data contract before runtime work | confirmed | `docs/architecture/data-contracts.md`, `docs/architecture/system1-ingestion.md`, `docs/validation/test-matrix.md` |
| MVP-0.5 status in durable matrix | confirmed | `docs/validation/test-matrix.md`, `scripts/bin/harness-cli query matrix` |
| SQLite WAL + FTS5 + FAISS + logical media refs architecture | confirmed | `docs/decisions/`, `docs/architecture/` |
| Query workflows, API shapes, fusion model, and UI contract | confirmed | `docs/product/*.md` |

## Not Yet Implemented In Runtime Code

| Area | State | Evidence |
| --- | --- | --- |
| Seed dataset fixture proving the contract is executable | planned | `docs/validation/test-matrix.md` MVP-0.6 |
| Runtime backend APIs | not implemented | no backend runtime slice in repo |
| React/Vite retrieval UI | not implemented | no frontend retrieval slice in repo |
| Search adapters and live fusion | not implemented | docs only |
| Agent runtime | not implemented | docs only |

## Interpretation Rule

This repository now has canonical docs sufficient to start implementation planning for `MVP-0.6 Seed Dataset Builder`. Do not claim runtime behavior exists unless code/tests prove it.
