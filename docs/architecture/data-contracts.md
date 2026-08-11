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
state, or FAISS result resolution. System 1 converts official videos and
optional organizer metadata into app-ready data, creates canonical metadata for
every video, and regenerates all derived retrieval evidence.

## Organizer Input Contract

The organizer makes these preliminary Batch 1 files available:

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

The project input policy is narrower: System 1 consumes only the official videos
and organizer metadata where available. It does not import organizer keyframes,
object JSON, CLIP features, media-info, or map-keyframes. System 1 regenerates
keyframes, objects, embeddings, timing mappings, captions, OCR, ASR, and scene
evidence under one project-owned provenance and frame-ID contract. It also owns
runtime SQLite, FTS5, FAISS, vector mapping, validation, and release packaging.

## Roots

The repo, large data, and hot runtime artifacts are separate.

| Root | Purpose | Notes |
| --- | --- | --- |
| `${REPO_ROOT}` | Source code, docs, config, schemas, small fixtures | Do not store real competition media here. |
| `${AIC_DATA_ROOT}` | External large-data root, usually HDD | Raw videos, canonical per-video metadata, source archives, and project-generated processed media live here. |
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
    metadata/
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
    siglip.faiss
    beit3.faiss
    vector_map.parquet
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
videos, one canonical metadata JSON per video, and raw-level inventory/import
manifests only:

```text
AIC26_raw/canonical_raw_vXXX/raw_videos/
AIC26_raw/canonical_raw_vXXX/metadata/
AIC26_raw/canonical_raw_vXXX/frame_timeline/{video_id}.parquet
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

`phase00_ingestion/reports/phase00_sync_manifest.json` is written last and is
the remote completion marker. Sync reconciles only that exact release/Phase00
prefix; it must not delete another release or an unrelated repo path.

## Canonical Per-Video Metadata

Organizer metadata is optional source evidence. Canonical project metadata is
not optional: every canonical video has exactly one
`metadata/{video_id}.json`, produced before raw upload by the package code used
by Notebook 00B/00C.

Observed organizer JSON fields are:

- `author`
- `channel_id`
- `channel_url`
- `description`
- `keywords`
- `length`
- `publish_date`
- `thumbnail_url`
- `title`
- `watch_url`

The canonical JSON contains those fields for every video plus
`schema_version`, `video_id`, `organizer_metadata_present`, a `media` object of
`ffprobe` facts, and a `provenance` object. Unknown organizer scalar values are
JSON `null`; unknown keywords are `[]`. `publish_date` uses ISO `YYYY-MM-DD`.
The package must not fabricate title/channel/URL values when organizer metadata
is absent.

Organizer `length` remains the source value in integer seconds.
`media.duration_sec` is the independent, normally more precise, `ffprobe`
measurement. The canonical HF prefix does not store a second organizer JSON.
The `provenance` object records the organizer source archive/member reference
and checksum when available; the original remains in source storage. See ADR
0016 for the complete shape and provenance rules.

`missing_metadata.json` records organizer metadata absence before canonical
JSON generation. The existence of `metadata/{video_id}.json` must therefore not
clear the missing-organizer audit. Downstream ingestion propagates
`organizer_metadata_present` and `metadata_generated`; it must not infer source
presence only from canonical file existence.

For backward compatibility, `metadata_generated=true` means organizer metadata
was absent and its canonical organizer-field section had to be filled with
null/empty values. It does not mean that only those videos receive canonical
JSON: the canonical JSON itself is generated for every video.

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
- `canonical_metadata_path`, always present for a valid canonical video
- `canonical_frame_timeline_path`
- `frame_timeline_status`
- `frame_timeline_row_count`
- `frame_timeline_size_bytes`
- `metadata_schema_version`
- `organizer_metadata_present`
- `metadata_generated`
- `duration_sec`
- `fps`
- `frame_count`
- `width`
- `height`
- `is_vfr`
- `file_size_bytes`
- `probe_status`
- `probe_attempts`

The inventory is a batch-friendly projection of the same canonical metadata
record. Validation requires their shared identifiers, provenance flags, and
probe facts to agree. HF canonical ingest uses this inventory for efficient
discovery and may reuse duration, FPS, frame count, dimensions, VFR status, and
file size. A required decoded timeline supplies the authoritative frame count
from its row count. Packet counting (`ffprobe -count_packets` /
`nb_read_packets`), header `nb_frames`, and duration/FPS math are compatibility
fallbacks. It must not download videos
only to repeat inventory probing. Notebook 00B/00C build the decoded timeline
while each video is already in bounded local scratch and upload the compact
Parquet beside the video and canonical metadata. Production canonical HF ingest
downloads and validates that Parquet instead of downloading the raw video to
decode it a second time.

The raw uploader makes at most three probe/timeline attempts with bounded retry
delays. In production `frame_timeline_policy=required`, exhausted timeline
attempts fail that video and therefore the run. Compatibility runs may use
`if-available` or `disabled`; unavailable probe facts remain nullable and are
never fabricated. Canonical JSON and inventory must agree on probe fields, and
the inventory timeline row count must agree with the uploaded Parquet.

## Data Categories

The app-ready contract covers these categories:

1. Raw videos
2. Canonical video metadata JSON, one per raw video
3. Project-generated keyframes
4. Thumbnails
5. Keyframe metadata
6. Captions
7. OCR text and optional boxes
8. ASR transcript segments
9. Object/concept detections
10. Scene/shot inspection context
11. SigLIP and BEiT3 image embeddings
12. Separate SigLIP and BEiT3 FAISS indexes
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
| `shots` | One row per TransNet V2 shot; a successful no-cut result is one valid full-video shot. Stores `shot_id`, `video_id`, final `scene_id`, frame/time ranges, detection method, and status. Production model/inference failure is not converted into a fallback shot. |
| `scenes` | Deterministic contiguous partitions of ordered shots. Production Phase01 uses the multimodal context-focus boundary design in `docs/architecture/system1-scene-grouping.md`; package code derives IDs, ranges, counts, mappings, status, and provenance. |
| `keyframes` | One row per keyframe; stores `keyframe_id`, `video_id`, `frame_id`, `shot_id`, `scene_id`, role/representative metadata, `time_seconds` or `timestamp_sec`, `pts_time`, `duration_time`, `frame_id_method`, `keyframe_ref`, `thumbnail_ref`. |
| `shot_captions` | Canonical shot-level caption evidence. Production Phase01 creates exactly one bilingual row per shot from the representative keyframe, with `caption_vi` and `caption_en`. |
| `scene_summaries` | Exactly one bilingual row per final Phase01 scene, with `summary_vi` and `summary_en`, built from ordered representative images, shot captions, transcript evidence, and timeline. |
| `ocr` | OCR evidence mapped to `keyframe_id`, with optional boxes/confidence. |
| `asr_segments` | Transcript segments mapped to `video_id` and time range. |
| `shot_transcript_links` | Canonical link rows between ASR segments and shots. |
| `scene_transcript_links` | Canonical link rows between ASR segments and scenes. |
| `objects` | Object/concept detections mapped to `keyframe_id`; text source type is `object_labels`. |
| `embeddings_meta` | Per-vector embedding provenance for the separate SigLIP and BEiT3 indexes. Rows are distinguished by `index_name` and model/version while resolving to the same canonical keyframes. |
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
- `shots`: `shot_id`, `video_id`, `scene_id`, `start_frame`, `end_frame`,
  `start_seconds`, `end_seconds`.
- `scenes`: `scene_id`, `video_id`, `start_frame`, `end_frame`,
  `start_seconds`, `end_seconds`, `start_shot_id`, `end_shot_id`, `shot_count`,
  grouping method/version/status, and `[start_frame, end_frame)` boundary
  convention.
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
- Every raw video has exactly one schema-valid canonical metadata JSON with the
  same filename stem.
- Organizer metadata, when present in source storage, matches exactly one raw
  video by filename stem and contributes source reference/checksum provenance
  without being copied into a second HF metadata tree.
- Missing organizer metadata is recorded before canonical generation and must
  not exclude a valid video from the app-ready dataset.
- Canonical metadata and `canonical_video_inventory.parquet` agree on video ID,
  provenance flags, and probed media facts.
- No organizer keyframe, object, CLIP, map-keyframes, or media-info artifact is
  imported into the app-ready release.
- No duplicate `video_id`.
- No duplicate `(video_id, frame_id)`.
- Every `videos.source_video_stem` equals `videos.video_id` for this dataset contract.
- Every video has probed `fps`; mismatch from expected `25` must be reported until current-year FPS is confirmed.
- Every `video_ref`, `keyframe_ref`, and `thumbnail_ref` resolves through `MediaStorePort`.
- Every production-included `frame_id` is the decoded original frame index from
  the Phase00 frame timeline. Estimated FPS mapping is debug-only and cannot
  satisfy app-ready validation.
- Every keyframe has `keyframe_ref` and `thumbnail_ref`.
- Every normal shot has distinct early/middle/late keyframes near
  20%/50%/80%; short shots emit every distinct decodable frame once; every shot
  has exactly one representative keyframe.
- Every SigLIP and BEiT3 FAISS vector has a corresponding `vector_map` row with
  the correct `index_name`.
- Every `vector_map.keyframe_id` exists in `keyframes`.
- Every shot has exactly one successful `shot_captions` row with non-empty
  `caption_vi` and `caption_en`, resolving to its representative keyframe.
- Every scene has exactly one successful `scene_summaries` row with non-empty
  `summary_vi` and `summary_en`.
- Every OCR/object row points to an existing keyframe.
- Every ASR segment points to an existing video.
- Every shot belongs to exactly one scene after production Phase01 grouping.
- Scenes partition each video's ordered shots without overlap, omission, or a
  gap in shot order; scene frame/time ranges equal their first/last shot ranges.
- Every keyframe's `scene_id` agrees with the scene assigned to its `shot_id`.
- Every scene-transcript link references existing scene and ASR rows.
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
- Small SigLIP/BEiT3-compatible vector-map fixtures, even if the actual FAISS
  indexes are stubbed for early tests.
- Validation report proving the seed dataset is app-ready.

## Open Questions

- Official Batch 2 dataset structure and final submission transport are not confirmed.
- Final object/OCR/ASR provider formats are not confirmed.
- Exact schema DDL will be finalized in `MVP-1 Runtime SQLite Schema + Validation`.
