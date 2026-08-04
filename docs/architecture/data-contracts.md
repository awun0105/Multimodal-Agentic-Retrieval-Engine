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

Organizer-provided files are not acceptable by themselves for runtime search,
state, or FAISS result resolution. System 1 must convert the official videos
and any useful validated support artifacts into app-ready data.

## Organizer Input Contract

The official preliminary Batch 1 dataset input for this project is:

1. raw `.mp4` video files;
2. organizer keyframes under per-video folders;
3. object JSON files per keyframe;
4. CLIP ViT-B/32 keyframe features in `.npy` files;
5. map-keyframes and media-info support files;
6. YouTube metadata JSON files where available.

Example pairing:

- `videos/L21_0001.mp4`
- `metadata/L21_0001.json`

The video filename stem, such as `L21_0001`, is the organizer dataset key and
the canonical `video_id` for this project. It does not depend on `watch_url`,
YouTube ID, or any online identifier.

The official videos are the base media source. Organizer keyframes, objects,
CLIP features, media-info, map-keyframes, and metadata are support inputs.
System 1 may import them with provenance after validating their mapping, and it
may generate better or additional retrieval artifacts from the videos. System 1
still owns runtime SQLite, FTS5, FAISS, vector mapping, generated or imported
evidence normalization, validation, and release packaging.

## Roots

The repo, large data, and hot runtime artifacts are separate.

| Root | Purpose | Notes |
| --- | --- | --- |
| `${REPO_ROOT}` | Source code, docs, config, schemas, small fixtures | Do not store real competition media here. |
| `${AIC_DATA_ROOT}` | External large-data root, usually HDD | Raw videos, organizer support artifacts, and processed media live here. |
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
    organizer_keyframes/
    organizer_objects/
    organizer_clip_features/
    organizer_metadata/
    organizer_maps/
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

## Hugging Face Storage Contract

System 1 shared storage uses two Hugging Face Dataset repos:

```text
AIC26_raw
AIC26_release
```

`AIC26_raw` is the canonical raw dataset repo. It stores standardized raw
videos, organizer support artifacts when mirrored, metadata when available, and
raw-level inventory/import manifests only:

```text
AIC26_raw/canonical_raw_vXXX/raw_videos/
AIC26_raw/canonical_raw_vXXX/organizer_keyframes/
AIC26_raw/canonical_raw_vXXX/organizer_objects/
AIC26_raw/canonical_raw_vXXX/organizer_clip_features/
AIC26_raw/canonical_raw_vXXX/organizer_metadata/
AIC26_raw/canonical_raw_vXXX/organizer_maps/
AIC26_raw/canonical_raw_vXXX/manifests/canonical_file_manifest.jsonl
AIC26_raw/canonical_raw_vXXX/manifests/canonical_import_report.json
AIC26_raw/canonical_raw_vXXX/manifests/canonical_video_inventory.parquet
AIC26_raw/canonical_raw_vXXX/manifests/missing_metadata.json
AIC26_raw/canonical_raw_vXXX/manifests/unmatched_metadata.json
```

`AIC26_release` is the processed workspace plus final release repo:

```text
AIC26_release/canonical_release_vXXX/phase00_ingestion/
AIC26_release/canonical_release_vXXX/phase01_structure/artifacts/{batch_id}/{video_id}_structure.zip
AIC26_release/canonical_release_vXXX/phase01_structure/worker_reports/
AIC26_release/canonical_release_vXXX/phase02_features/artifacts/{batch_id}/{video_id}_features.zip
AIC26_release/canonical_release_vXXX/phase02_features/worker_reports/
AIC26_release/canonical_release_vXXX/phase03_merged/
AIC26_release/canonical_release_vXXX/releases/
AIC26_release/canonical_release_vXXX/checkpoints/
AIC26_release/canonical_release_vXXX/logs/
```

Local package commands currently write artifact ZIPs and worker reports under:

```text
artifacts/structure/{video_id}_structure.zip
artifacts/features/{video_id}_features.zip
manifests/worker_reports/
```

The phase01/phase02 Hugging Face paths above are the shared target layout for a
separate sync/restore workflow. They are not a statement that the local package
commands upload phase01/phase02 artifacts directly to Hugging Face.

`phase00_ingestion` contains Notebook 00 ingestion and batch-planning outputs.
It is not a final runtime release. The final app-ready release for System 2 is:

```text
AIC26_release/canonical_release_vXXX/releases/competition_dataset_vXXX/
```

`missing_metadata.json` and `unmatched_metadata.json` are raw-level audit
manifests in `AIC26_raw`. The release repo may also snapshot them under
`phase00_ingestion/reports/` for a particular release run. Their authoritative
source of truth is:

```text
AIC26_raw/canonical_raw_vXXX/manifests/
```

Legacy flat layout under
`canonical_release_vXXX/{manifests,tables,raw_mapping}` is deprecated. New
outputs must use
`canonical_release_vXXX/phase00_ingestion/{manifests,tables,raw_mapping,frame_timeline,reports}`.

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

Last-year dataset evidence shows videos at 25 fps. Treat `25` as the planning/default expected FPS only. For AIC 2026 frame-id safety, System 1 should use decoded `frame_timeline` rows as the primary mapping between `frame_id`, `pts_time`, and duration. Packet counts and probed FPS are fallback evidence, not a reason to hard-code `/25` or silently derive exact frame ids from `frame_id / fps`.

## Logical Media References

SQLite stores logical refs only. It must not store absolute or machine-specific paths.

| Asset | Ref Pattern | Example |
| --- | --- | --- |
| Video | `raw_videos/{video_id}.mp4` | `raw_videos/L01_V028.mp4` |
| Keyframe | `keyframes/{video_id}/{video_id}_f{frame_id:07d}.jpg` | `keyframes/L01_V028/L01_V028_f0025300.jpg` |
| Thumbnail | `thumbnails/{video_id}/{video_id}_f{frame_id:07d}.webp` | `thumbnails/L01_V028/L01_V028_f0025300.webp` |

Backend resolves refs through `MediaStorePort`. MVP implementation is `LocalFileMediaStore` using `${AIC_DATA_ROOT}`. MinIO is optional future work behind the same port.

## Canonical Raw Upload Inventory

The versioned raw Hugging Face Dataset prefix includes a small probe inventory
beside the canonical file manifest:

```text
<raw_import_id>/manifests/canonical_video_inventory.parquet
```

This inventory is produced while `upload-standardized-raw` has local access to
`raw_videos/`, or while `stream-standardize-upload-raw` has one extracted pair
in local scratch. It must contain one row per canonical video with:

- `video_id`
- `canonical_repo_id`
- `canonical_repo_type`
- `canonical_revision`
- `canonical_prefix`
- `canonical_video_path`
- `canonical_metadata_path` when metadata exists, otherwise null with
  `metadata_missing` recorded in raw audit manifests
- `duration_sec`
- `fps`
- `frame_count`
- `file_size_bytes`

HF canonical ingest uses this inventory for duration, FPS, frame count, and
file size. Frame count should be produced from actual packet counting
(`ffprobe -count_packets` / `nb_read_packets`) when possible; header
`nb_frames` and duration/FPS math are fallbacks. It must not download
`raw_videos/*.mp4` only to probe media unless a debug/operator fallback
explicitly enables that behavior.

## Data Categories

The app-ready contract covers these categories:

1. Raw videos
2. Optional video metadata JSON matched by stem when available
3. Generated and/or imported keyframes
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
| `scenes` | Scene-level inspection context derived from consecutive shots, canonical shot captions, ASR/transcript rows, metadata, and timeline continuity. |
| `keyframes` | One row per keyframe; stores `keyframe_id`, `video_id`, `frame_id`, `shot_id`, `scene_id`, role/representative metadata, `time_seconds` or `timestamp_sec`, `pts_time`, `duration_time`, `frame_id_method`, `keyframe_ref`, `thumbnail_ref`. |
| `shot_captions` | Canonical shot-level caption evidence. Production Phase01 creates exactly one caption per shot from the representative keyframe. |
| `scene_summaries` | Phase01 scene summaries built from shot captions, transcript links, timeline continuity, and metadata. |
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

## Temporal Retrieval Readiness

System 1 does not need to publish a dedicated `temporal_search.parquet`
source-of-truth table. Temporal retrieval in System 2 should be computed from
the canonical runtime tables below.

Minimum temporal-ready fields:

- `videos`: `video_id`, `video_ref`, duration/FPS/VFR metadata.
- `shots`: `shot_id`, `video_id`, `start_frame`, `end_frame`, `start_seconds`,
  `end_seconds`.
- `scenes`: `scene_id`, `video_id`, `start_frame`, `end_frame`,
  `start_seconds`, `end_seconds`, and scene-to-shot grouping context such as
  `shot_ids` when available.
- `keyframes`: `keyframe_id`, `video_id`, `frame_id`, `shot_id`, `scene_id`,
  `time_seconds` and/or `timestamp_sec`, `pts_time`, `duration_time`,
  `keyframe_ref`, `thumbnail_ref`.
- `asr_segments`: `asr_segment_id`, `video_id`, `start_sec`, `end_sec`,
  `text`.
- `shot_transcript_links` and `scene_transcript_links`: canonical overlap/link
  rows from transcript evidence into shot/scene intervals.
- `shot_captions`, `scene_summaries`, `ocr`, and `objects`: searchable evidence
  rows that resolve back to
  `keyframe_id`, `shot_id`, `scene_id`, or `video_id`.
- `text_documents`: the global text-search contract used by FTS5.
- `vector_map`: the visual-search mapping used to resolve FAISS hits into
  keyframes before temporal reasoning.

Runtime-specific optimization views or tables are allowed, for example a
materialized same-video timeline view for faster temporal joins, but those are
derived caches only. They must not replace the canonical tables above as the
source of truth.

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

- Every raw video has a unique canonical `video_id` derived from its filename
  stem.
- Metadata JSON files, when present, match exactly one raw video by filename
  stem.
- Missing metadata is recorded as optional evidence absence and must not exclude
  a valid video from the app-ready dataset.
- Organizer support artifacts imported into the release resolve to known
  `video_id` / `frame_id` values, or are excluded with a validation warning.
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
- Optional matching metadata JSON, plus at least one fixture case where missing
  metadata does not remove the video.
- Multiple keyframes for the video.
- Thumbnails for those keyframes.
- At least one caption row.
- At least one OCR row.
- At least one ASR segment.
- At least one object/concept row.
- A small FAISS-compatible vector-map fixture, even if the actual FAISS index is stubbed for early tests.
- Validation report proving the seed dataset is app-ready.

## Open Questions

- Official Batch 2 dataset structure and final submission transport are not confirmed.
- Final object/OCR/ASR provider formats are not confirmed.
- Exact schema DDL will be finalized in `MVP-1 Runtime SQLite Schema + Validation`.
