# 0003 Preprocessing Warehouse: DuckDB

Date: 2026-06-12

## Status

Accepted

## Context

Preprocessing needs bulk import, staging, joins, validation, statistics, and
artifact preparation across CSV, JSON, and Parquet. These jobs are separate
from runtime app-state concerns.

## Decision

Use DuckDB for preprocessing, staging, analytics, validation, and bulk metadata
warehouse responsibilities.

DuckDB is not the MVP runtime application database.

## Alternatives Considered

1. SQLite-only for preprocessing and runtime.
2. DuckDB as both preprocessing and runtime store.
3. Pandas-only file processing without a warehouse layer.

## Consequences

Positive:

- Gives fast local analytics and bulk processing.
- Keeps rebuildable preprocessing separate from runtime state.
- Supports validation reports and optional Parquet export.

Tradeoffs:

- Adds one more database technology to the stack.
- Requires clear artifact boundaries between DuckDB outputs and SQLite runtime.

## Follow-Up

- Reflect DuckDB staging flow in `docs/architecture/ingestion.md`.
- Use DuckDB outputs to prepare SQLite, FAISS, and FTS5 artifacts.
