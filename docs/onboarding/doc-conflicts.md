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

- Target docs/spec now define Notebook 01 / `process-batch` as phase01
  semantic structure: restore phase00, reuse phase00 video facts, process only
  the assigned batch, stage per-video raw media from `AIC26_raw` or local input,
  generate TransNet V2 shot boundaries, selected keyframes, thumbnails, one
  representative keyframe per shot, one canonical `shot_captions` row per shot,
  required ASR/transcript rows, shot transcript links, scenes, scene summaries,
  structure ZIPs, worker report, and sync to `phase01_structure`.
- Current package implementation can produce valid structure ZIPs and reports,
  and the fallback scaffold now consumes Phase00 decoded frame timelines when
  available through provider interfaces. The package layout now follows the
  one-shot-caption-per-shot contract: `shot_captions` is produced in Phase01,
  Phase02 no longer produces caption/enriched-summary artifacts, and merge
  combines Phase01 text evidence with Phase02 feature evidence.
- The remaining gap is provider/algorithmic implementation depth: the current
  package still uses fallback/provider-scaffold behavior for production
  algorithms such as TransNet V2 shot detection, full representative-keyframe
  selection policy, mandatory real ASR, VLM shot captioning, and LLM scene
  summarization.

Partially resolved. File naming, package layout, canonical Phase01
shot-caption ownership, Phase02 caption removal, and timeline-aware fallback
interfaces have been migrated toward the target phase01 contract. Real provider
implementations and algorithm integrations remain open package work and must
not move into Notebook 01 cells.

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
