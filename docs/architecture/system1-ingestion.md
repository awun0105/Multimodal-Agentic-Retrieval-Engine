# System 1: Ingestion And Preprocessing

## Status

Canonical for offline preprocessing. System 1 produces the app-ready contract in `docs/architecture/data-contracts.md` and never serves live user queries.

## Responsibility

System 1 is required because organizer input contains only raw `.mp4` videos and per-video metadata JSON. It converts those inputs plus project-generated signals into validated app-ready artifacts. System 2 reads only SQLite, FTS5 tables, FAISS indexes, and logical media refs produced by this system.

```text
raw video folder + metadata JSON folder
  -> dataset registration
  -> dataset pairing by filename stem
  -> media discovery
  -> metadata normalization
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
| Dataset pairing | paired input manifest | Match raw videos and metadata JSON by the same filename stem; use that stem as `video_id`; fail on missing, extra, or duplicate stems. |
| Media discovery | `videos`, discovered media manifest | Discover videos from configurable roots; do not hardcode personal paths or filename regexes. |
| Metadata normalization | normalized staging tables | Preserve raw metadata; normalize title, author/channel, duration, publish date, keywords, description, watch URL, and thumbnail URL. |
| Video probing | probed media facts | Probe fps, duration, dimensions, codec/container facts; last-year evidence suggests 25 fps, but actual fps must be persisted per video. |
| Timeline mapping | `frame_timeline` staging rows or equivalent mapping proof | Persist enough timing metadata to map timestamps to frame ids safely, especially for VFR or unreliable FPS metadata. |
| Shot detection | `shots` rows | If shot detection fails but the video is otherwise readable, emit a fallback full-video shot and mark degraded status instead of dropping the whole video immediately. |
| Keyframe extraction | `keyframes` rows and media refs | Generate keyframes from raw videos; use `keyframe_id = "{video_id}:{frame_id}"`; compute timestamps from actual probed fps; store logical refs only. |
| Thumbnail generation | `thumbnail_ref` per keyframe | Generate missing thumbnails under `${AIC_DATA_ROOT}/processed/media/thumbnails/`. |
| Minimum keyframe/image captioning | `image_captions` rows | If semantic scene construction uses visual captions, these minimum caption rows are phase01 structure inputs and must exist before scene construction. Provider/model choice is config-driven. |
| Scene construction | `scenes` rows | Scenes enrich inspection/runtime context and may use shots, selected keyframes, minimum keyframe/image captions, ASR/transcript rows, and metadata. Scene boundary must snap to shot boundary. |
| OCR import/generation | `ocr`, `text_documents` | Preserve confidence and optional boxes when available; global text search is built later from `text_documents`. |
| ASR import/generation | `asr_segments`, `text_documents` | ASR is usually time-range evidence on `video_id`; canonical links are shot/scene transcript links. |
| Caption enrichment | `image_captions` additive rows, `shot_captions`, `text_documents` | Phase02 may add heavier/additional image captions and shot captions, but phase01 scene construction must not depend on Notebook 02. |
| Object/concept import | `objects`, `text_documents` | Preserve label, score, optional box, source, and model/version. |
| Embedding import/generation | FAISS index + `vector_map` | FAISS rows must resolve through SQLite before returning results. |
| Validation | validation report and failure status | App-ready build is usable only when required checks pass. |

Notebook 01 / phase01 workers should reuse phase00 probe facts from
`tables/videos.parquet` and `raw_mapping/media_store_manifest.parquet`.
Phase01 may verify or stage the current video when needed, but it should not
re-probe every video or copy the full raw dataset into worker runtime storage.

## CLI Contract

Preprocessing must be runnable from batch CLI scripts. Minimum interface:

```text
aic-prepare build \
  --dataset-id aic2026 \
  --raw-video-dir ${AIC_DATA_ROOT}/raw/videos \
  --metadata-dir ${AIC_DATA_ROOT}/raw/metadata_original \
  --data-root ${AIC_DATA_ROOT} \
  --runtime-root ${AIC_RUNTIME_ROOT} \
  --report ${AIC_DATA_ROOT}/staging/reports/aic2026-validation.json
```

CLI rules:

- Accept input roots and output roots as config or flags.
- Treat the raw video stem as canonical `video_id` after uniqueness validation.
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

The earlier `data/` tree in source material is a logical artifact layout, not a physical repository layout. Raw videos are referenced by `video_ref = raw_videos/{video_id}.mp4` and are resolved through `MediaStorePort`; compact releases may omit raw-video copies. `frame_timeline` is staging/debug and may be per-video, merged, sampled, or omitted from compact release when key tables retain enough frame/timestamp mapping fields.

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
- `canonical_metadata_path`
- `duration_sec`
- `fps`
- `frame_count`
- `file_size_bytes`

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
raw videos, metadata, and raw-level import/inventory manifests:

```text
AIC26_raw/canonical_raw_vXXX/raw_videos/
AIC26_raw/canonical_raw_vXXX/metadata/
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
`canonical_release_vXXX/phase00_ingestion/{manifests,tables,raw_mapping,reports}`.

Google Drive may be used as an organizer handoff source or local operator
scratch area. It is not the primary shared storage contract.

Notebook 00B uses the streaming path for Colab free CPU runs: it scans zip
members to build a pairing plan, extracts video/metadata pair batches bounded
by `RAW_UPLOAD_BATCH_SIZE` files and scratch bytes into local scratch, probes
those local files, uploads each batch to `AIC26_raw` with the same batched HF
commit helper as canonical raw upload, records per-pair progress, and cleans the
scratch batch before moving on. It does not materialize a full standardized
`raw_videos/` and `metadata/` tree on Drive.

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
- Every raw video has exactly one metadata JSON with the same stem, and every metadata JSON has exactly one raw video.
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
