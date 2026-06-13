# Documentation Conflicts

## Conflict 1: Runtime DB/Search Layer

- `README.md`: states `DB: SQLite` and `Text/object search: SQLite FTS5`.
- Earlier source material also discussed DuckDB/Tantivy/OpenSearch alternatives.
- User decision on 2026-06-12: canonical architecture is SQLite WAL + FTS5 for runtime and DuckDB for preprocessing/staging/analytics.

Resolved. Use SQLite WAL + SQLite FTS5 for runtime application state and text search. Use DuckDB for preprocessing, staging, analytics, validation, and bulk metadata warehouse work.

## Conflict 2: Keyframe ID Format

- Older docs/examples used underscore-style identifiers such as `old underscore-style keyframe example`.
- The archived root data-contract draft introduced `keyframe_id = "{video_id}:{frame_id}"`.

Resolved. Canonical keyframe identifier is colon-based. Underscore-style examples are stale and must not appear in canonical runtime/API docs.

## Conflict 3: `legacy video-name field` vs `video_id`

- Some source docs say `video name` or `legacy video-name field`.
- Canonical DB/API contract needs one stable field name.

Resolved. Use `video_id` as the canonical field in DB, API, UI, and docs. `legacy video-name field` may appear only when quoting or explaining legacy source wording.

## Conflict 4: Logical `data/` Tree vs Physical Storage Roots

- Older source material used `old repo-local SQLite path`, `old repo-local FAISS path`, and `old repo-local media path` examples.
- The app-ready contract separates repo code from external data and runtime roots.

Resolved. Physical roots are `${AIC_DATA_ROOT}` for large media/staging artifacts and `${AIC_RUNTIME_ROOT}` for hot runtime artifacts. Any `data/` tree is logical documentation shorthand only.

## Conflict 5: Media Storage Backend

- Archived ingestion reference introduced a MediaStore abstraction and optional MinIO.
- User decision on 2026-06-12: LocalFileMediaStore for MVP; MinIO optional future adapter only.

Resolved. MVP uses local filesystem media storage through `LocalFileMediaStore`. MinIO remains an optional future adapter and is not part of MVP.

## Conflict 6: Text Search Engine Scope

- `README.md`: `Text/object search: SQLite FTS5`.
- Archived ingestion reference described SQLite FTS5 first.
- Archived data-ready reference mentioned SQLite FTS5 or Tantivy.
- User decision on 2026-06-12: SQLite FTS5 is the MVP text search layer; Tantivy/OpenSearch/BM25 JSON are future or historical alternatives.

Resolved. Use SQLite FTS5 as MVP text search. Treat Tantivy/OpenSearch/BM25 JSON as future or historical alternatives only.
