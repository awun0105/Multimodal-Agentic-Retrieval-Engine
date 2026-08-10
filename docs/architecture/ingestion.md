# Ingestion Architecture

## Status

Canonical planning document for ingestion architecture. Derived from archived ingestion references plus accepted project decisions.

## Source-of-Truth Rules

- `docs/architecture/system1-ingestion.md` is the canonical System 1 ingestion architecture source for future implementation planning.
- Archived source inputs are historical only and are not required for implementation.

## Goal

Transform official/raw dataset inputs into runtime-ready artifacts for the local
retrieval app.

```text
official data
  -> staging/normalization/validation
  -> SQLite runtime artifacts + FAISS + SQLite FTS5 + media assets
  -> app can search and inspect without raw-folder scanning
```

## Canonical Storage Split

### Runtime

Use SQLite WAL + SQLite FTS5 as the runtime application database and text-search layer.

Runtime SQLite scope:

- app state
- query sessions
- query clues
- search history
- candidates
- agent runs
- metadata lookup
- vector ID mapping
- bilingual shot captions and scene summaries
- OCR
- ASR
- objects
- FTS5 tables

### Preprocessing / Warehouse

Use DuckDB for:

- bulk import from CSV/JSON/Parquet
- preprocessing staging tables
- metadata joins and normalization
- dataset completeness validation
- statistics and reports
- preparing artifacts for SQLite, FAISS, and FTS5
- optional Parquet export

DuckDB is rebuildable staging/analytics infrastructure, not the MVP runtime app-state store.

### Vector Search

Use FAISS for the visual/vector index. Runtime SQLite stores vector-to-keyframe mappings.

### Media Storage

Use local filesystem for MVP media assets:

- raw videos
- keyframes
- thumbnails
- generated assets

MinIO is an optional future adapter only.

## App-Ready Artifact Contract

The ingestion pipeline should prepare:

- runtime SQLite database with validated lookup tables and app/session tables
- FTS5-backed text search contract built from global `text_documents` inside `app.sqlite`
- separate SigLIP and BEiT3 FAISS visual indexes
- local media paths/URIs for videos, keyframes, thumbnails, and generated assets
- validation reports for completeness and mapping integrity

## Canonical Input Strategy

Input layout must stay flexible at the file-extension level. The organizer
publishes videos and baseline support artifacts, but this project's canonical
input policy consumes official videos plus organizer metadata when available,
creates one canonical metadata JSON for every video, and regenerates all
derived evidence.

Required organizer inputs:

- raw videos

Optional organizer input:

- metadata JSON files matched to videos by stem when available

Required project-owned raw output:

- `metadata/{video_id}.json` for every video, normalized from the ten observed
  organizer fields plus `ffprobe` media facts and provenance according to ADR
  0016
- preserved original organizer JSON when present
- pre-generation missing/unmatched organizer metadata audit manifests

Explicitly unused organizer support material:

- organizer keyframes and map-keyframes/media-info
- organizer object JSON and CLIP features

Derived project-generated inputs or artifacts may include:

- extracted keyframes
- generated embeddings
- object detection files
- OCR/ASR/caption files

## Validation Responsibilities

Ingestion validation should catch:

- missing video files
- metadata JSON without a matching raw video stem
- missing keyframes
- missing thumbnails when expected
- duplicate video/frame IDs
- invalid local paths/URIs
- FAISS rows without SQLite mapping
- SQLite keyframes without media assets
- evidence rows pointing to unknown frames or videos

## MVP Ingestion Order

1. Scan dataset inputs.
2. Import/stage in DuckDB.
3. Normalize canonical per-video metadata and retain organizer provenance.
4. Produce runtime SQLite tables.
5. Build SQLite FTS5 tables.
6. Build/load separate SigLIP and BEiT3 FAISS indexes.
7. Validate local file paths and mapping integrity.
8. Write validation reports.

## Deferred or Optional

- MinIO adapter
- Tantivy/OpenSearch
- LVLM verification
- advanced rerankers
- hard-coded submission/export outputs
- mandatory preview video generation
