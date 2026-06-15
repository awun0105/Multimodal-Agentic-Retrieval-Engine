# App-ready Data Contract

## Status

Canonical. This document is the source of truth for the app-ready data contract; the earlier root draft has been archived.

See also: `docs/architecture/storage-strategy.md`.

This document defines the app-ready artifact contract that must exist before building runtime backend, UI, retrieval, or agent features.

## Principle

Runtime code must not infer dataset structure from raw files.

System 1 converts raw organizer inputs into app-ready artifacts. System 2 reads only those app-ready artifacts.

| Layer | Canonical Role |
| --- | --- |
| JSON / CSV / Parquet | Raw input, staging output, manifests, validation reports, intermediate artifacts |
| SQLite WAL | Runtime catalog, app state, query sessions, candidates, vector mapping, relational evidence |
| SQLite FTS5 | Runtime text search contract built from global `text_documents` inside `app.sqlite` |
| FAISS | Runtime vector index |
| Filesystem | Large media assets: videos, keyframes, thumbnails |
| DuckDB | Offline preprocessing, staging, analytics, validation |

Organizer-provided raw videos plus JSON metadata are not acceptable by themselves for runtime search, state, or FAISS result resolution.

## Organizer Input Contract

The official dataset input for this project is:

1. a folder of raw `.mp4` video files;
2. a folder of metadata JSON files;
3. one metadata JSON per raw video;
4. raw video and metadata matched by the same filename stem.

Example pairing:

- `videos/L21_0001.mp4`
- `metadata/L21_0001.json`

The stem, such as `L21_0001`, is the organizer dataset key and the canonical `video_id` for this project. It does not depend on `watch_url`, YouTube ID, or any online identifier.

Organizer input does not include derived retrieval artifacts such as keyframes, embeddings, FAISS indexes, OCR, ASR, object detections, or runtime SQLite databases. Those are project-generated System 1 outputs.

## Roots

The repo, large data, and hot runtime artifacts are separate.

| Root | Purpose | Notes |
| --- | --- | --- |
| `${REPO_ROOT}` | Source code, docs, config, schemas, small fixtures | Do not store real competition media here. |
| `${AIC_DATA_ROOT}` | External large-data root, usually HDD | Raw videos/metadata and processed media live here. |
| `${AIC_RUNTIME_ROOT}` | Runtime hot artifact root, preferably SSD | SQLite, FAISS, and runtime cache live here. |

## Physical Layout

```text
${REPO_ROOT}/
  system1/
  system2/
    backend/
    frontend/
  docs/
  scripts/
  docs/archived/
  ui-ideas/

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
  staging/
    staging.duckdb

${AIC_RUNTIME_ROOT}/
  db/
    app.sqlite
  indexes/
    visual.faiss
    index_version.json
  cache/
```

Any earlier `data/` tree in docs should be read as a logical app-ready artifact layout, not as repository layout.

## Canonical IDs

| ID | Format | Example | Notes |
| --- | --- | --- | --- |
| `dataset_id` | Stable dataset/version key | `aic2026` | Groups one app-ready dataset. |
| `video_id` | Organizer file stem, unique within dataset | `L21_0001` | Primary video identifier and user-facing submit/debug key. |
| `frame_id` | Integer frame number | `25300` | Frame number in the video. |
| `keyframe_id` | `{video_id}:{frame_id}` | `L01_V028:25300` | Canonical keyframe key. |
| `vector_id` | FAISS row integer | `123456` | Resolved through SQLite `vector_map`. |
| `video_ref` | Canonical raw-video logical ref | `raw_videos/L01_V028.mp4` | Never absolute. |
| `keyframe_ref` | Canonical keyframe logical ref | `keyframes/L01_V028/L01_V028_f0025300.jpg` | Never absolute. |
| `thumbnail_ref` | Canonical thumbnail logical ref | `thumbnails/L01_V028/L01_V028_f0025300.webp` | Never absolute. |
| `media_ref` | Generic adapter/media abstraction field | `keyframes/L01_V028/L01_V028_f0025300.jpg` | Use only where a table truly needs one abstract media column. |

`video_id` is derived from the raw video filename stem and must not be derived from `watch_url`. `video_id + frame_id` remains the user-facing submit/copy unit. `keyframe_id` is the DB/API glue key.

Last-year dataset evidence shows videos at 25 fps. Treat `25` as the planning/default expected FPS, but System 1 must probe each raw video, persist actual `fps`, and compute `timestamp_sec = frame_id / actual_fps`. Do not hard-code `/25` as a universal runtime rule before current-year media is verified.

## Logical Media References

SQLite stores logical refs only. It must not store absolute or machine-specific paths.

| Asset | Ref Pattern | Example |
| --- | --- | --- |
| Video | `raw_videos/{video_id}.mp4` | `raw_videos/L01_V028.mp4` |
| Keyframe | `keyframes/{video_id}/{video_id}_f{frame_id:07d}.jpg` | `keyframes/L01_V028/L01_V028_f0025300.jpg` |
| Thumbnail | `thumbnails/{video_id}/{video_id}_f{frame_id:07d}.webp` | `thumbnails/L01_V028/L01_V028_f0025300.webp` |

Backend resolves refs through `MediaStorePort`. MVP implementation is `LocalFileMediaStore` using `${AIC_DATA_ROOT}`. MinIO is optional future work behind the same port.

## Data Categories

The app-ready contract covers these categories:

1. Raw videos
2. Video metadata JSON matched by stem
3. Generated keyframes
4. Thumbnails
5. Keyframe metadata
6. Captions
7. OCR text and optional boxes
8. ASR transcript segments
9. Object/concept detections
10. Scene/shot inspection context
11. Image embeddings
12. FAISS index
13. Vector mapping
14. Feature availability
15. Query sessions
16. Query clues
17. Search runs/results
18. Candidates
19. Agent runs/steps
20. Validation reports/manifests

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
| `videos` | One row per video; stores `video_id`, `source_video_stem`, `video_ref`, duration, fps, VFR/frame-count metadata, dimensions, normalized metadata, and selected raw metadata fields. |
| `shots` | One row per shot or fallback full-video shot; stores `shot_id`, `video_id`, frame/time ranges, detection method, and degraded/full-fidelity status. |
| `scenes` | Scene-level inspection context derived from shots and metadata/ASR; enriches runtime inspection but should not control MVP keyframe extraction. |
| `keyframes` | One row per keyframe; stores `keyframe_id`, `video_id`, `frame_id`, `timestamp_sec`, `pts_time`, `frame_id_method`, `keyframe_ref`, `thumbnail_ref`. |
| `image_captions` | Caption evidence mapped to image/keyframe. |
| `shot_captions` | Caption evidence mapped to shot-level intervals. |
| `ocr` | OCR evidence mapped to `keyframe_id`, with optional boxes/confidence. |
| `asr_segments` | Transcript segments mapped to `video_id` and time range. |
| `shot_transcript_links` | Canonical link rows between ASR segments and shots. |
| `scene_transcript_links` | Canonical link rows between ASR segments and scenes. |
| `objects` | Object/concept detections mapped to `keyframe_id`; text source type is `object_labels`. |
| `embeddings_meta` | Registered embedding/index metadata: name, model, dimension, metric, path/ref. |
| `vector_map` | Mandatory mapping from `(index_name, vector_id)` to `keyframe_id`, `video_id`, `frame_id`. |
| `feature_availability` | Runtime/UI convenience table describing whether ASR/OCR/object/caption/inspection evidence exists per entity and whether it is pass/degraded/missing/failed. |
| `release_capabilities` | Dataset/release capability flags for runtime gating and degraded behavior. |
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

FTS5-backed text search is built from global `text_documents`; per-source FTS tables are optional implementation details only.

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

- Every raw video has exactly one metadata JSON with the same filename stem.
- Every metadata JSON has exactly one raw video with the same filename stem.
- No duplicate `video_id`.
- No duplicate `(video_id, frame_id)`.
- Every `videos.source_video_stem` equals `videos.video_id` for this dataset contract.
- Every video has probed `fps`; mismatch from expected `25` must be reported until current-year FPS is confirmed.
- Every `video_ref`, `keyframe_ref`, and `thumbnail_ref` resolves through `MediaStorePort`.
- `frame_id` uses decoded original frame index when available; fallback timestamp-to-fps mapping must be marked estimated/degraded when it is the only method.
- Every keyframe has `keyframe_ref` and `thumbnail_ref`.
- Every FAISS vector has a corresponding `vector_map` row.
- Every `vector_map.keyframe_id` exists in `keyframes`.
- Every caption/OCR/object row points to an existing keyframe.
- Every ASR segment points to an existing video.
- SQLite contains no absolute paths.
- SQLite contains no machine-specific paths.
- FTS5 row counts match source relational tables or documented expectations.

## Seed Dataset Requirement

Before runtime implementation, the project needs a tiny seed dataset under `system1/tests/fixtures/` or equivalent. It should include:

- At least one video record.
- Its matching metadata JSON.
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
