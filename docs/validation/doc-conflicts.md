# Documentation Conflicts

## Conflict 1: Runtime DB/Search Layer

- `README.md`: states `DB: SQLite` and `Text/object search: SQLite FTS5`.
- Earlier source material also discussed DuckDB/Tantivy/OpenSearch alternatives.
- User decision on 2026-06-12: canonical architecture is SQLite WAL + FTS5 for runtime and DuckDB for preprocessing/staging/analytics.

Resolved. Use SQLite WAL + SQLite FTS5 for runtime application state and text search. Use DuckDB for preprocessing, staging, analytics, validation, and bulk metadata staging/preprocessing work.

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

## Conflict 7: Phase01 semantic structure target vs current fallback implementation

Resolved 2026-10-26: the old Phase01 command and modules were removed (plan
`system1-pipeline-simplification` Step 6); the worker path in ADR 0023 and
`docs/architecture/system1-target.md` replaces them. The pre-removal text is in
Git history and in `docs/archive/system1-notebook01-production-pipeline.md`.

## Conflict 8: Optional Organizer Metadata vs Required Canonical Metadata

- Official organizer metadata is optional and may be absent for a video.
- Older package behavior generated only a minimal placeholder for missing
  metadata and could make downstream code infer provenance from file presence.
- ADR 0016 requires one project-owned canonical metadata JSON for every video,
  whether organizer metadata exists or not.

Resolved at the contract level. Notebook 00B/00C package code must read
organizer JSON when present, retain its source reference/checksum when
available, probe every video with `ffprobe`, generate and validate the same
canonical schema for every video, and retain the pre-generation
missing/unmatched audits. The HF raw prefix does not contain a duplicate
organizer metadata tree. Unknown organizer scalar values remain `null`,
`keywords` remains an empty list, and organizer values must not be fabricated.
Implementation and executable proof are still pending, so this resolution must
not be read as current code readiness.

## Conflict 9: Runtime Tables Before And After ADR 0021 to 0026

- `data-contracts.md` before 2026-10-26 listed 23 runtime tables (`shot_captions`,
  `scene_summaries`, `*_transcript_links`, `objects`, `embeddings_meta`,
  `feature_availability`, query and agent state tables) and schemas under
  `system1/schemas/*.schema.json` matched that pipeline.
- The worker and release code since commit `93c7723` write `cut_segments`,
  `shots`, `keyframes`, `text_documents` and FAISS vector maps as Parquet.

Resolved 2026-10-26. `data-contracts.md` now describes `release_v2`
(`videos`, `cut_segments`, `shots`, `scenes`, `keyframes`, `text_documents`,
`text_documents_fts`, `vector_map`) with schemas in `system1/schemas/v2/`.
Query and agent state tables are System 2 runtime state
(`system2-retrieval.md`). Old schemas and the modules that read them are
removed in plan Step 6. Worker packages are `worker_package_v2` with
`is_representative`; `shots.scene_id` is null in packages and set by the
release builder (plan Step 5b items 1 and 5).

## Conflict 10: Old System 1 Architecture Documents vs ADRs 0021 to 0026

- `system1-spec.md`, `system1-throughput.md`,
  `system1-notebook01-production-pipeline.md`, `system1-scene-grouping.md`,
  `data-contracts-explainer.md`, and the Phase01/Phase02 parts of
  `system1-ingestion.md` described the removed pipeline and carried
  "being superseded" notes.

Resolved 2026-10-26 (plan Step 6 item 3). Those files moved to `docs/archive/`
with a "superseded by" header. `system1-ingestion.md` now covers Phase00 only.
Live System 1 docs: `system1-target.md`, `system1-ingestion.md`,
`data-contracts.md`, ADRs 0021 to 0026. ADR 0014 and ADR 0015 still link to the
old `docs/architecture/` paths of archived files.
