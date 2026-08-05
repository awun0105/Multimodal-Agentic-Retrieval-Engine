# 0001 Runtime Database: SQLite WAL

Date: 2026-06-12

## Status

Accepted

## Context

The MVP needs a local/LAN runtime database for application state, query workflows,
and text search. The runtime path must stay simple, debuggable, and stable under
competition pressure.

## Decision

Use SQLite with WAL mode as the MVP runtime source of truth.

Runtime SQLite scope includes:

- app state
- query sessions
- query clues
- search history
- candidates
- agent runs
- metadata lookup
- vector ID mapping
- shot_captions
- scene_summaries
- OCR
- ASR
- objects
- SQLite FTS5 tables for text search

Runtime pragmas:

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;
```

Optional tuning:

```sql
PRAGMA temp_store=MEMORY;
PRAGMA mmap_size=<machine dependent>;
```

## Alternatives Considered

1. SQLite-only for all runtime and preprocessing concerns.
2. DuckDB as the runtime application database.
3. PostgreSQL or heavier client/server databases.

## Consequences

Positive:

- Keeps runtime local-first and easy to deploy.
- Supports multi-session LAN use with simple write coordination.
- Keeps text search close to application data.

Tradeoffs:

- Requires explicit write discipline under concurrent use.
- Large bulk preprocessing is better handled outside runtime SQLite.

## Follow-Up

- Reflect WAL + FTS5 runtime rules in architecture and ingestion docs.
- Define runtime schema in MVP-1.
