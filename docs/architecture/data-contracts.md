# App-ready Data Contract

## Status

Canonical. This document is the source of truth for the app-ready data contract; the earlier root draft has been archived.

See also: `docs/architecture/storage-strategy.md`.

This document defines the app-ready artifact contract that must exist before building runtime backend, UI, retrieval, or agent features.

## Principle

Runtime code must not infer dataset structure from raw files.

System 1 converts raw organizer data into app-ready artifacts. System 2 reads only those app-ready artifacts.

| Layer | Canonical Role |
| --- | --- |
| JSON / CSV / Parquet | Raw input, staging output, manifests, validation reports, intermediate artifacts |
| SQLite WAL | Runtime catalog, app state, query sessions, candidates, vector mapping, relational evidence |
| SQLite FTS5 | Runtime text index for captions, OCR, ASR, metadata, objects |
| FAISS | Runtime vector index |
| Filesystem | Large media assets: videos, keyframes, thumbnails |
| DuckDB | Offline preprocessing, staging, analytics, validation |

JSON-only metadata is not acceptable for runtime search, state, or FAISS result resolution.

## Roots

The repo, large data, and hot runtime artifacts are separate.

| Root | Purpose | Notes |
| --- | --- | --- |
| `${REPO_ROOT}` | Source code, docs, config, schemas, small fixtures | Do not store real competition media here. |
| `${AIC_DATA_ROOT}` | External large-data root, usually HDD | Raw videos/keyframes and processed media live here. |
| `${AIC_RUNTIME_ROOT}` | Runtime hot artifact root, preferably SSD | SQLite, FAISS, and runtime cache live here. |

## Physical Layout

```text
${REPO_ROOT}/
  backend/
  frontend/
  docs/
  scripts/
  notebooks/
  config/
  schemas/
  tests/fixtures/tiny_seed_dataset/

${AIC_DATA_ROOT}/
  raw/
    videos/
    keyframes_original/
    metadata_original/
  processed/
    media/
      videos/
      keyframes/
      thumbnails/
  staging/
    shards/
    reports/
  warehouse/
    warehouse.duckdb

${AIC_RUNTIME_ROOT}/
  db/
    app.sqlite
  indexes/
    visual.faiss
    visual_index_manifest.json
  cache/
```

Any earlier `data/` tree in docs should be read as a logical app-ready artifact layout, not as repository layout.

## Canonical IDs

| ID | Format | Example | Notes |
| --- | --- | --- | --- |
| `dataset_id` | Stable dataset/version key | `aic2026` | Groups one app-ready dataset. |
| `video_id` | Video name without extension | `L01_V028` | Primary video identifier. |
| `frame_id` | Integer frame number | `25300` | Official frame ID if provided. |
| `keyframe_id` | `{video_id}:{frame_id}` | `L01_V028:25300` | Canonical keyframe key. |
| `vector_id` | FAISS row integer | `123456` | Resolved through SQLite `vector_map`. |
| `media_ref` | Logical relative path | `keyframes/L01_V028/025300.jpg` | Never absolute. |

`video_id + frame_id` remains the user-facing submit/copy unit. `keyframe_id` is the DB/API glue key.

## Logical Media References

SQLite stores logical refs only. It must not store absolute or machine-specific paths.

| Asset | Ref Pattern | Example |
| --- | --- | --- |
| Video | `videos/{video_id}.mp4` | `videos/L01_V028.mp4` |
| Keyframe | `keyframes/{video_id}/{frame_id_padded}.jpg` | `keyframes/L01_V028/025300.jpg` |
| Thumbnail | `thumbnails/{video_id}/{frame_id_padded}.webp` | `thumbnails/L01_V028/025300.webp` |

Backend resolves refs through `MediaStorePort`. MVP implementation is `LocalFileMediaStore` using `${AIC_DATA_ROOT}`. MinIO is optional future work behind the same port.

## Data Categories

The app-ready contract covers these categories:

1. Raw videos
2. Official/generated keyframes
3. Thumbnails
4. Video metadata
5. Keyframe metadata
6. Captions
7. OCR text and optional boxes
8. ASR transcript segments
9. Object/concept detections
10. Scene/location/attribute tags
11. Image embeddings
12. FAISS index
13. Vector mapping
14. Query sessions
15. Query clues
16. Search runs/results
17. Candidates
18. Agent runs/steps
19. Validation reports/manifests

## Runtime SQLite Schema

Runtime SQLite is the source of truth for app-readable metadata, search mapping, and user/agent state.

Required pragmas:

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;
```

Machine-specific tuning such as `temp_store` or `mmap_size` is allowed but must not be required for correctness.

### Required Tables

| Table | Purpose |
| --- | --- |
| `datasets` | Dataset identity and build metadata. |
| `videos` | One row per video; stores `video_ref`, duration, fps, dimensions, metadata. |
| `keyframes` | One row per keyframe; stores `keyframe_id`, `video_id`, `frame_id`, `timestamp_sec`, `keyframe_ref`, `thumbnail_ref`. |
| `captions` | Caption evidence mapped to `keyframe_id`. |
| `ocr_texts` | OCR evidence mapped to `keyframe_id`, with optional boxes/confidence. |
| `asr_segments` | Transcript segments mapped to `video_id` and time range; optional keyframe alignment through `keyframe_asr_segments`. |
| `keyframe_asr_segments` | Optional many-to-many alignment between keyframes and ASR segments. |
| `objects` | Object/concept detections mapped to `keyframe_id`. |
| `scene_tags` | Optional scene, location, or attribute tags mapped to `keyframe_id`. |
| `embedding_indexes` | Registered vector index metadata: name, model, dimension, metric, path/ref. |
| `vector_map` | Mandatory mapping from `(index_name, vector_id)` to `keyframe_id`, `video_id`, `frame_id`. |
| `query_sessions` | Human/team query session state. |
| `query_clues` | Clues/questions attached to a query session. |
| `search_runs` | Search execution metadata and parameters. |
| `search_results` | Ranked result snapshots for reproducibility/debugging. |
| `candidates` | Saved candidate answers/frames. |
| `agent_runs` | Automatic mode run metadata. |
| `agent_steps` | Automatic mode trace steps. |

## FTS5 Tables

Runtime text search uses SQLite FTS5 inside `app.sqlite`.

Required FTS5 tables:

- `caption_fts`
- `ocr_fts`
- `asr_fts`
- `object_fts`
- `metadata_fts`

Optional unified table:

- `evidence_fts`

FTS5 queries must return `keyframe_id` or `video_id`, then backend joins relational tables to produce UI-ready results.

## FAISS Mapping Contract

FAISS only returns vector row IDs. It does not know videos or frames.

Canonical resolution flow:

```text
FAISS vector_id
  -> SQLite vector_map(index_name, vector_id)
  -> keyframe_id
  -> video_id + frame_id
  -> keyframe_ref + thumbnail_ref
  -> caption/OCR/ASR/object evidence
```

`vector_map` is mandatory runtime data. A Parquet or JSON mapping file may exist as a staging/debug artifact, but it is not the runtime source of truth.

## App-ready Dataset Validation

A dataset is app-ready only when validation proves all required checks pass.

Required checks:

- No duplicate `video_id`.
- No duplicate `(video_id, frame_id)`.
- Every `media_ref` resolves through `MediaStorePort`.
- Every keyframe has `keyframe_ref` and `thumbnail_ref`.
- Every FAISS vector has a corresponding `vector_map` row.
- Every `vector_map.keyframe_id` exists in `keyframes`.
- Every caption/OCR/object row points to an existing keyframe.
- Every ASR segment points to an existing video.
- SQLite contains no absolute paths.
- SQLite contains no machine-specific paths.
- FTS5 row counts match source relational tables or documented expectations.

## Seed Dataset Requirement

Before runtime implementation, the project needs a tiny seed dataset under `tests/fixtures/tiny_seed_dataset/` or equivalent. It should include:

- At least one video record.
- Multiple keyframes for the video.
- Thumbnails for those keyframes.
- At least one caption row.
- At least one OCR row.
- At least one ASR segment.
- At least one object/concept row.
- A small FAISS-compatible vector-map fixture, even if the actual FAISS index is stubbed for early tests.
- Validation report proving the seed dataset is app-ready.

## Open Questions

- Official AIC 2026 dataset structure and submission format are not confirmed.
- Final object/OCR/ASR provider formats are not confirmed.
- Exact schema DDL will be finalized in `MVP-1 Runtime SQLite Schema + Validation`.
