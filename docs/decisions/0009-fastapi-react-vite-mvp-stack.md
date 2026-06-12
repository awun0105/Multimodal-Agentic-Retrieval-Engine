# 0009 FastAPI + React/Vite MVP Stack

Date: 2026-06-12

## Status

Accepted

## Context

The MVP needs one backend service and one browser SPA with clean boundaries for
local/LAN deployment.

## Decision

Adopt this MVP stack:

- Frontend: React/Vite SPA
- Backend: FastAPI
- Runtime DB: SQLite WAL
- Text Search: SQLite FTS5
- Preprocessing/Staging: DuckDB
- Vector Search: FAISS
- Media Storage: LocalFileMediaStore

## Alternatives Considered

1. Multiple dashboards or frontend apps.
2. Microservices from day one.
3. Heavier search or storage infrastructure in MVP.

## Consequences

Positive:

- Keeps MVP focused and implementable.
- Aligns with Single Web UI + Multi-session Workflow.
- Preserves room for future adapters without bloating MVP.

Tradeoffs:

- Some advanced capabilities are explicitly deferred.
- The MVP must resist premature infrastructure growth.

## Follow-Up

- Use this stack in backlog ordering and validation planning.
- Keep non-MVP items out of early implementation stories.
