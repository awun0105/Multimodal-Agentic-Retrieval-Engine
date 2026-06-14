# Current State

## Status

Canonical state-of-project snapshot as of 2026-06-13.

See `docs/product/requirements-truth-set.md` for the current confirmed requirements, planning assumptions, unknowns, and MVP out-of-scope boundaries.

## Implemented In Docs And Matrix

| Area | State | Evidence |
| --- | --- | --- |
| Product framing as one Web UI plus Query Sessions | confirmed | `README.md`, `docs/architecture/overview.md`, `docs/product/query-workflows.md` |
| MVP runtime targets are local single-machine mode and one-host LAN mode for teammate browser access | confirmed | `README.md`, `docs/architecture/overview.md`, `docs/stories/acceptance-criteria.md` |
| Organizer dataset input is raw videos plus per-video metadata JSON only | confirmed | human-provided dataset detail, `docs/architecture/data-contracts.md`, `docs/architecture/system1-ingestion.md` |
| Raw video format is `.mp4` | confirmed | human-provided dataset detail, `docs/product/requirements-truth-set.md` |
| Raw video and metadata JSON are paired by matching filename stem; that stem is canonical `video_id` | confirmed | human-provided dataset detail, `docs/architecture/data-contracts.md` |
| Last-year dataset videos were observed at 25 fps; current planning uses 25 fps as expected/default while System 1 still probes actual fps per video | planning assumption from prior dataset evidence | `docs/architecture/data-contracts.md`, `docs/architecture/system1-ingestion.md` |
| App-ready data contract before runtime work | confirmed | `docs/architecture/data-contracts.md`, `docs/architecture/system1-ingestion.md`, `docs/validation/test-matrix.md` |
| MVP-0.5 status in durable matrix | confirmed | `docs/validation/test-matrix.md`, `scripts/bin/harness-cli query matrix` |
| SQLite WAL + FTS5 + FAISS + logical media refs architecture | confirmed | `docs/decisions/`, `docs/architecture/` |
| Query workflows, API shapes, fusion model, and UI contract | confirmed | `docs/product/*.md` |
| Final-round workflow expects organizer API submission with human-editable answer drafts and submission history | confirmed as product requirement; exact organizer API details unknown | `docs/product/query-workflows.md`, `docs/product/api-contracts.md`, `docs/architecture/system2-retrieval.md` |
| Final-round operation uses public-screen progressive reveal; competitors manually operate their team system | confirmed | `docs/product/requirements-truth-set.md`, `docs/product/query-workflows.md` |
| Internet/external services are allowed, but core retrieval remains local/LAN-first and artifact-backed | confirmed allowance plus planning boundary | `docs/product/requirements-truth-set.md`, `docs/product/rules-2026.md` |
| 2026 task types are not official yet; planning temporarily assumes last-year-style Textual KIS, VKIS, Q&A, and TRAKE | planning assumption | `docs/product/query-workflows.md`, `docs/product/queries-and-agent.md` |

## Not Yet Implemented In Runtime Code

| Area | State | Evidence |
| --- | --- | --- |
| Seed dataset fixture proving raw-video/metadata pairing and app-ready artifact generation | planned | `docs/validation/test-matrix.md` MVP-0.6 |
| Runtime backend APIs | not implemented | no backend runtime slice in repo |
| React/Vite retrieval UI | not implemented | no frontend retrieval slice in repo |
| Search adapters and live fusion | not implemented | docs only |
| Agent runtime | not implemented | docs only |
| Organizer submission API adapter | not implemented | official endpoint/auth/payload are unknown |
| Local/LAN runtime packaging and host run workflow | not implemented | docs define target modes, but no runnable app exists yet |

## Interpretation Rule

This repository now has canonical docs sufficient to start implementation planning for `MVP-0.6 Seed Dataset Builder`. Do not claim runtime behavior exists unless code/tests prove it. Do not claim organizer-provided keyframes, features, OCR, ASR, objects, FAISS indexes, or runtime databases exist unless current dataset evidence proves it. Do not treat 2026 task formats, submission payloads, or scoring feedback as final until official rules/API docs exist. Submit responsibility is a team process outside the MVP app, not an auth/role feature.
