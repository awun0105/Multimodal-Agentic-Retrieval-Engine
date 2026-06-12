# Documentation Conflicts

## Conflict 1: Metadata Database Choice

### Area

Ingestion and storage architecture.

### Conflict

Earlier documents disagreed on whether MVP metadata/runtime storage should use
DuckDB, SQLite, or both.

### Evidence

- `DATA_READY.md`: proposes `metadata.duckdb` plus `app.sqlite`.
- `README.md`: states `DB: SQLite` and `Text/object search: SQLite FTS5`.
- `docs/references/original-sources/INGESTION.md`: centers the runtime around SQLite artifacts.
- User decision on 2026-06-12: canonical architecture is SQLite WAL + FTS5 for runtime and DuckDB for preprocessing/staging/analytics.

### Proposed Resolution

Resolved. Use SQLite WAL + SQLite FTS5 for runtime application state and text
search. Use DuckDB for preprocessing, staging, analytics, validation, and bulk metadata warehouse work.

### Human Confirmation Needed

No. Resolved by explicit user decision.

## Conflict 2: Original Ingestion Draft vs V2 Ingestion

### Area

Ingestion pipeline and normalized artifact contract.

### Conflict

The original ingestion draft and the later ingestion reference described different ingestion directions.

### Evidence

- Historical ingestion draft: older System 1/System 2 draft and JSON-heavy artifact model.
- `docs/references/original-sources/INGESTION.md`: simplified architecture with SQLite/FAISS/local media and flexible inputs.
- User decision on 2026-06-12: treat `docs/references/original-sources/INGESTION.md` as canonical for future implementation planning.

### Proposed Resolution

Resolved. `docs/architecture/system1-ingestion.md` is canonical for planning. `docs/references/original-sources/INGESTION.md` is reference-only source material.

### Human Confirmation Needed

No. Resolved by explicit user decision.

## Conflict 3: MinIO Optionality

### Area

Media storage.

### Conflict

Some documents introduced MinIO, but MVP simplicity and local-first constraints
made its status unclear.

### Evidence

- `docs/references/original-sources/INGESTION.md`: introduces a MediaStore abstraction and optional MinIO.
- `README.md` and `SPEC.md`: emphasize local/LAN simplicity.
- User decision on 2026-06-12: LocalFileMediaStore for MVP; MinIO optional future adapter only.

### Proposed Resolution

Resolved. MVP uses local filesystem media storage through `LocalFileMediaStore`. MinIO remains an optional future adapter and is not part of MVP.

### Human Confirmation Needed

No. Resolved by explicit user decision.

## Conflict 4: Test Matrix vs Product Scope

### Area

Validation planning.

### Conflict

`SPEC.md` defines broad product scope, but the repo has no implementation and the
original test matrix had no real rows.

### Evidence

- `SPEC.md`: broad product scope.
- Repo audit: docs-only, no runtime code or tests.
- User decision on 2026-06-12: add concrete test-matrix rows for MVP-0 to MVP-3 first; later behavior stays planned.

### Proposed Resolution

Resolved for onboarding. The test matrix should contain concrete planned rows for MVP-0 through MVP-3 only. Later behaviors remain planned, not implemented.

### Human Confirmation Needed

No. Resolved by explicit user decision.

## Conflict 5: Text Search Engine Direction

### Area

Text search implementation.

### Conflict

Older drafts referenced BM25/JSON sparse search, while newer docs and runtime
constraints prefer SQLite FTS5 for MVP.

### Evidence

- Historical ingestion draft: BM25/JSON-style sparse retrieval direction.
- `README.md`: `Text/object search: SQLite FTS5`.
- `docs/references/original-sources/INGESTION.md`: `indexes/text.sqlite` using SQLite FTS5 first.
- `DATA_READY.md`: SQLite FTS5 or Tantivy.
- User decision on 2026-06-12: SQLite FTS5 is the MVP text search layer; Tantivy/OpenSearch/BM25 JSON are future or historical alternatives.

### Proposed Resolution

Resolved. Use SQLite FTS5 as MVP text search. Treat Tantivy/OpenSearch/BM25 JSON as future or historical alternatives only.

### Human Confirmation Needed

No. Resolved by explicit user decision.
