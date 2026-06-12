# Ingestion Architecture

## Status

Canonical planning document for ingestion architecture. Derived from archived ingestion references plus accepted project decisions.

## Source-of-Truth Rules

- `docs/architecture/system1-ingestion.md` is the canonical System 1 ingestion architecture source for future implementation planning.
- `docs/references/original-sources/INGESTION.md` is reference-only source material.
- `docs/references/original-sources/DATA_READY.md` is reference-only source material.

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
- captions
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
- SQLite FTS5 tables for captions/OCR/ASR/metadata/objects
- FAISS visual index
- local media paths/URIs for videos, keyframes, thumbnails, and generated assets
- validation reports for completeness and mapping integrity

## Canonical Input Strategy

Input layout must stay flexible because official 2026 details are not confirmed.
The importer should detect available folders/files and skip missing optional
sources cleanly.

Possible inputs include:

- raw videos
- official keyframes
- official embeddings
- metadata JSON/CSV/Parquet
- object detection files
- OCR/ASR/caption files if provided

## Validation Responsibilities

Ingestion validation should catch:

- missing video files
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
3. Normalize and validate metadata in DuckDB.
4. Produce runtime SQLite tables.
5. Build SQLite FTS5 tables.
6. Build/load FAISS index.
7. Validate local file paths and mapping integrity.
8. Write validation reports.

## Deferred or Optional

- MinIO adapter
- Tantivy/OpenSearch
- LVLM verification
- advanced rerankers
- hard-coded submission/export outputs
- mandatory preview video generation
