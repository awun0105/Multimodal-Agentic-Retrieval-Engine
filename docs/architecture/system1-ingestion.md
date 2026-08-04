# System 1: Ingestion And Preprocessing

## Status

Canonical for offline preprocessing. System 1 produces the app-ready contract in `docs/architecture/data-contracts.md` and never serves live user queries.

## Responsibility

System 1 is required because organizer input is not app-ready runtime data. For
the preliminary Batch 1 profile, the official videos are the base media source
and the organizer also provides support artifacts such as keyframes, objects,
CLIP features, media-info, map-keyframes, and metadata when available. System 1
converts official videos, useful validated support artifacts, and
project-generated signals into app-ready artifacts. System 2 reads only SQLite,
FTS5 tables, FAISS indexes, and logical media refs produced by this system.

```text
official videos + useful validated organizer support artifacts
  -> dataset registration
  -> video identity and support-artifact mapping
  -> media discovery
  -> optional metadata normalization
  -> support artifact import with provenance
  -> structure artifact per video
  -> feature artifact per video
  -> merge structural + feature artifacts
  -> global text document construction
  -> SQLite WAL + FTS5 build
  -> FAISS + vector_map build
  -> DuckDB staging and validation
  -> validation reports + release package
```

## Required Stages

| Stage | Required Output | Notes |
| --- | --- | --- |
| Dataset registration | `datasets` row and build manifest | Assign stable `dataset_id`, source version, build time, and source roots. |
| Dataset mapping | input manifest | Use the raw video filename stem as `video_id`; fail on duplicate video stems; record missing metadata as optional evidence absence; exclude or warn on support artifacts that cannot map to a known video/frame. |
| Media discovery | `videos`, discovered media manifest | Discover videos from configurable roots; do not hardcode personal paths or filename regexes. |
| Metadata normalization | normalized staging tables | Preserve raw metadata when present; normalize title, author/channel, duration, publish date, keywords, description, watch URL, and thumbnail URL. Missing metadata must not remove the video. |
| Support artifact import | organizer keyframe/object/CLIP staging tables | Import organizer keyframes, map-keyframes, media-info, object JSON, and CLIP ViT-B/32 features only after validating `video_id`, `frame_id`, vector count/order, and provenance. |
| Video probing | probed media facts | Probe fps, duration, dimensions, codec/container facts; last-year evidence suggests 25 fps, but actual fps must be persisted per video. |
| Timeline mapping | `frame_timeline` staging rows or equivalent mapping proof | Persist enough timing metadata to map timestamps to frame ids safely, especially for VFR or unreliable FPS metadata. |
| Shot detection | `shots` rows | Production Phase01 standardizes on TransNet V2 as the shot-boundary provider. Package code may keep a provider interface for testability, but production notebooks should not expose multiple shot-detection modes. |
| Keyframe extraction | `keyframes` rows and media refs | Generate one or more keyframes per shot, such as early/middle/late, and mark one representative keyframe per shot for shot captioning. Use `keyframe_id = "{video_id}:{frame_id}"`; role is metadata, not part of the ID. Prefer decoded `frame_timeline` rows for `frame_id`/timestamp mapping, with FPS math only as a marked fallback; store logical refs only. |
| Thumbnail generation | `thumbnail_ref` per keyframe | Generate missing thumbnails under `${AIC_DATA_ROOT}/processed/media/thumbnails/`. |
| Shot captioning | `shot_captions` rows | Phase01 creates exactly one canonical caption per shot from that shot's representative keyframe. All frames/keyframes in the shot inherit this caption by joining through `shot_id`; do not create per-keyframe captions as the canonical scene input. |
| Scene construction | `scenes` rows | Scenes enrich inspection/runtime context and use consecutive shots, shot captions, ASR/transcript rows, metadata, and timeline continuity. Scene boundary must snap to shot boundary. |
| OCR import/generation | `ocr`, `text_documents` | Preserve confidence and optional boxes when available; global text search is built later from `text_documents`. |
| ASR import/generation | `asr_segments`, `text_documents` | ASR is required in production Phase01. It is time-range evidence on `video_id`; canonical links are shot/scene transcript links. Test/mock profiles may emit schema-valid placeholders, but production runs should fail or mark the video failed/degraded when ASR cannot be produced. |
| Feature extraction | `embeddings_meta`, `ocr`, `objects`, `text_sources`, FAISS inputs | Phase02 extracts non-caption features only: visual embeddings, OCR, object/concept detections, and their text-source rows. It does not create canonical shot captions or enriched scene summaries. |
| Object/concept import | `objects`, `text_documents` | Preserve label, score, optional box, source, and model/version. |
| Embedding import/generation | FAISS index + `vector_map` | FAISS rows must resolve through SQLite before returning results. |
| Validation | validation report and failure status | App-ready build is usable only when required checks pass. |

Notebook 01 / phase01 workers should reuse phase00 probe facts from
`tables/videos.parquet`, `raw_mapping/media_store_manifest.parquet`, and
`frame_timeline/{video_id}.parquet` when available. Phase01 may verify or stage
the current video when needed, but it should not re-probe every video or copy
the full raw dataset into worker runtime storage. When a decoded timeline is
missing, the structure artifact should carry a degraded/warning status rather
than silently deriving exact frame ids in notebook code.

## CLI Contract

Preprocessing must be runnable from batch CLI scripts. Minimum interface:

```text
aic-prepare build \
  --dataset-id aic2026 \
  --raw-video-dir ${AIC_DATA_ROOT}/raw/videos \
  --metadata-dir ${AIC_DATA_ROOT}/raw/organizer_metadata \
  --organizer-keyframes-dir ${AIC_DATA_ROOT}/raw/organizer_keyframes \
  --organizer-objects-dir ${AIC_DATA_ROOT}/raw/organizer_objects \
  --organizer-clip-features-dir ${AIC_DATA_ROOT}/raw/organizer_clip_features \
  --organizer-maps-dir ${AIC_DATA_ROOT}/raw/organizer_maps \
  --data-root ${AIC_DATA_ROOT} \
  --runtime-root ${AIC_RUNTIME_ROOT} \
  --report ${AIC_DATA_ROOT}/staging/reports/aic2026-validation.json
```

CLI rules:

- Accept input roots and output roots as config or flags.
- Treat the raw video stem as canonical `video_id` after uniqueness validation.
- Treat organizer support artifact roots as optional inputs that must validate
  before they become app-ready evidence.
- Do not derive `video_id` from `watch_url`, YouTube ID, title, or channel metadata.
- Treat `video_ref` as the canonical logical raw-video reference.
- Treat `keyframe_ref` and `thumbnail_ref` as canonical logical refs for derived images.
- Write large media/staging artifacts under `${AIC_DATA_ROOT}`.
- Write hot runtime artifacts under `${AIC_RUNTIME_ROOT}`.
- Emit machine-readable validation reports.
- Fail non-zero when required validation checks fail.
- Support resumable shard processing for long-running OCR/ASR/embedding jobs.
- Never require absolute paths embedded in SQLite.

## Artifact Outputs

```text
${AIC_DATA_ROOT}/raw/videos/{video_id}.mp4
${AIC_DATA_ROOT}/processed/media/keyframes/{video_id}/{video_id}_f{frame_id:07d}.jpg
${AIC_DATA_ROOT}/processed/media/thumbnails/{video_id}/{video_id}_f{frame_id:07d}.webp
${AIC_DATA_ROOT}/staging/frame_timeline/{video_id}.parquet
${AIC_DATA_ROOT}/staging/staging.duckdb
${AIC_DATA_ROOT}/staging/reports/{dataset_id}-validation.json
${AIC_RUNTIME_ROOT}/db/app.sqlite
${AIC_RUNTIME_ROOT}/indexes/visual.faiss
${AIC_RUNTIME_ROOT}/indexes/index_version.json
```

The earlier `data/` tree in source material is a logical artifact layout, not a
physical repository layout. Raw videos are referenced by
`video_ref = raw_videos/{video_id}.mp4` and are resolved through
`MediaStorePort`. A preliminary-ready release must provide managed video access
and an exact-frame resolver for System 2 inspection. It may avoid duplicating
video bytes when `MediaStorePort` can resolve the referenced videos reliably.
`frame_timeline` is staging/debug and may be per-video, merged, sampled, or
omitted from compact release when key tables retain enough frame/timestamp
mapping fields and System 2 can still resolve exact frame IDs.

For the versioned raw Hugging Face Dataset path, `upload-standardized-raw` and
the Colab-oriented `stream-standardize-upload-raw` emit
`manifests/canonical_video_inventory.parquet` with one row per video.
The inventory carries:

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

`frame_count` should come from `ffprobe -count_packets` / `nb_read_packets`
when available. Header `nb_frames` and duration/FPS math are fallbacks, with
math estimates marked degraded because frame IDs may drift.

Canonical HF ingest consumes that inventory by default and does not download
`raw_videos/*.mp4` solely for media probing unless
`AIC_ALLOW_HF_VIDEO_DOWNLOAD_FOR_PROBE=1` is set.

## Hugging Face Shared Storage Contract

System 1 uses exactly two Hugging Face Dataset repos for shared state:

```text
AIC26_raw
AIC26_release
```

`AIC26_raw` is the canonical raw dataset repo. It contains only standardized
raw videos, mirrored organizer support artifacts when used, metadata when
available, and raw-level import/inventory manifests:

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

`AIC26_raw` does not contain structure artifacts, feature artifacts, merged
tables, `app.sqlite`, FAISS, final releases, or run-specific batch planning
files.

`AIC26_release` is the processed workspace plus final release repo. It is not
only the final release folder:

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

Local package commands currently write:

```text
artifacts/structure/{video_id}_structure.zip
artifacts/features/{video_id}_features.zip
manifests/worker_reports/
```

The phase01/phase02 Hugging Face paths are target storage for a separate
sync/restore workflow, not direct upload behavior of the local package commands.

Notebook 00 writes phase00 ingestion outputs to:

```text
AIC26_release/canonical_release_vXXX/phase00_ingestion/tables/videos.parquet
AIC26_release/canonical_release_vXXX/phase00_ingestion/raw_mapping/media_store_manifest.parquet
AIC26_release/canonical_release_vXXX/phase00_ingestion/frame_timeline/{video_id}.parquet
AIC26_release/canonical_release_vXXX/phase00_ingestion/manifests/frame_timeline_manifest.parquet
AIC26_release/canonical_release_vXXX/phase00_ingestion/manifests/batch_manifest.csv
AIC26_release/canonical_release_vXXX/phase00_ingestion/manifests/batch_*.txt
AIC26_release/canonical_release_vXXX/phase00_ingestion/reports/
```

`missing_metadata.json` and `unmatched_metadata.json` are raw-level audit
manifests in `AIC26_raw`. The release repo may also snapshot them under
`phase00_ingestion/reports/` for a particular release run. Their authoritative
source of truth is:

```text
AIC26_raw/canonical_raw_vXXX/manifests/
```

Legacy flat paths under:

```text
canonical_release_vXXX/manifests
canonical_release_vXXX/tables
canonical_release_vXXX/raw_mapping
```

are deprecated. New output must use
`canonical_release_vXXX/phase00_ingestion/{manifests,tables,raw_mapping,frame_timeline,reports}`.

Google Drive may be used as an organizer handoff source or local operator
scratch area. It is not the primary shared storage contract.

Notebook 00B uses the streaming path for Colab free CPU runs: it scans zip
members to build an official-source import plan, extracts bounded video and
available support-artifact batches into local scratch, probes local videos,
uploads each batch to `AIC26_raw` with the same batched HF commit helper as
canonical raw upload, records per-video progress, and cleans the scratch batch
before moving on. It does not materialize a full standardized raw tree on Drive.

The streaming path exposes the same disk-safe option family as archive
standardization: `--min-free-gb`, `--drive-sync-sleep-seconds`,
`--cleanup-every-files`, and `--cleanup-every-gb`. Notebook 00B uses these
options to keep local scratch bounded while preserving batched Hugging Face
commits.

Notebook 00C uses the same streaming path for local laptop/workstation runs.
The source is a local downloaded zip folder, so the notebook skips Google Drive
mount/remount and `drive-shadow`, then continues with HF raw upload, canonical
HF ingest, batch assignment, and `phase00_ingestion` sync.

## Validation Gate

System 1 must prove:

- No duplicate `video_id` and no duplicate `(video_id, frame_id)`.
- Every raw video has a unique canonical `video_id` derived from its filename
  stem.
- Metadata JSON files, when present, match exactly one raw video by filename
  stem. Missing metadata is recorded as optional evidence absence and must not
  exclude a valid video.
- Organizer support artifacts imported into the release resolve to known
  `video_id` / `frame_id` values, or are excluded with a validation warning.
- Every video has probed fps; non-25 fps is reported against the planning/default expected value until current-year FPS is confirmed.
- Every `keyframe_id` matches `"{video_id}:{frame_id}"`.
- Every `video_ref`, `keyframe_ref`, and `thumbnail_ref` resolves through `MediaStorePort`.
- `frame_id` uses decoded original frame index when available; fallback `timestamp * fps` mapping must be marked as estimated/degraded when it is the only available method.
- Runtime SQLite includes `vector_map`, `feature_availability`, and enough logical refs for System 2 inspection flows.
- Every keyframe has a thumbnail ref.
- Every FAISS vector has a `vector_map` row.
- Every `vector_map.keyframe_id` exists in `keyframes`.
- Caption, OCR, and object rows point to existing keyframes.
- ASR rows point to existing videos and valid time ranges.
- SQLite contains no absolute or machine-specific paths.
- FTS5 row counts match source relational tables or documented expectations.
