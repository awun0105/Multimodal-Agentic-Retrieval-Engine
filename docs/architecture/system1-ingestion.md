# System 1: Ingestion And Preprocessing

## Status

Canonical for offline preprocessing. System 1 produces the app-ready contract in `docs/architecture/data-contracts.md` and never serves live user queries.

## Responsibility

System 1 is required because organizer input is not app-ready runtime data. The
organizer provides videos, optional metadata, and baseline support artifacts,
but the accepted project policy consumes only the videos and organizer
metadata. System 1 creates canonical metadata for every video and regenerates
every derived retrieval signal under one mapping/provenance contract. System 2
reads only SQLite, FTS5 tables, FAISS indexes, and logical media refs produced
by this system.

```text
official videos + optional organizer metadata
  -> dataset registration
  -> media discovery
  -> ffprobe facts + canonical metadata for every video
  -> video identity and decoded frame timeline
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
| Dataset mapping | input manifest | Use the raw video filename stem as `video_id`; fail on duplicate video stems; record missing organizer metadata before canonical metadata generation. |
| Media discovery | `videos`, discovered media manifest | Discover videos from configurable roots; do not hardcode personal paths or filename regexes. |
| Metadata normalization | `metadata/{video_id}.json` and normalized staging fields | Create one versioned canonical JSON per video. Normalize the ten observed organizer fields, retain source reference/checksum when available, use null/empty values when absent, and attach `ffprobe` media facts and provenance. Do not upload a duplicate organizer metadata tree. Missing organizer metadata must not remove the video. |
| Video probing | probed media facts | Probe fps, duration, dimensions, codec/container facts; last-year evidence suggests 25 fps, but actual fps must be persisted per video. |
| Timeline mapping | `frame_timeline` staging rows or equivalent mapping proof | Persist enough timing metadata to map timestamps to frame ids safely, especially for VFR or unreliable FPS metadata. |
| Shot detection | `shots` rows | Production Phase01 uses TransNet V2 only. A successful no-cut result is one valid full-video shot; model/inference failure after bounded retry fails the video instead of invoking a silent fallback. |
| Keyframe extraction | `keyframes` rows and media refs | Keep early/middle/late anchors near 20/50/80 percent of each shot and select the representative with the existing quality policy. Long shots may add bounded non-representative supplemental frames from timestamp probes only when cheap visual/text novelty is new. Use decoded original `frame_id` and `keyframe_id = "{video_id}:{frame_id}"`; short shots emit each distinct decodable frame once rather than duplicate IDs. |
| Thumbnail generation | `thumbnail_ref` per keyframe | Generate missing thumbnails under `${AIC_DATA_ROOT}/processed/media/thumbnails/`. |
| Shot captioning | `shot_captions` rows | Gemini returns strict `caption_vi`/`caption_en` JSON for exactly one canonical row per shot from the representative keyframe. Requests are cached, retried, rate-limited, resumable, and versioned; persistent production failure fails the video. |
| Scene construction | `scenes` rows | Production Phase01 uses `docs/architecture/system1-scene-grouping.md`. Gemini judges only adjacent-shot boundaries from ordered visual/bilingual-caption/ASR/timeline evidence; package code owns the deterministic partition and production failure is explicit. |
| OCR generation | `ocr`, `text_documents` | Notebook 02 runs Gemini OCR on project-generated keyframes and preserves confidence/boxes when returned. |
| ASR generation | `asr_segments`, `text_documents` | Notebook 01 defaults to faster-whisper large-v3 with automatic language and VAD. It can optionally use the pinned NeMo/Parakeet Vietnamese provider, which segments speech with FFmpeg silence detection before transcription. `no_audio`/`no_speech` produce empty schema-valid tables; extraction/inference failure after bounded retry fails the video. |
| Feature extraction | `embeddings_meta`, `ocr`, `objects`, `text_sources`, FAISS inputs | Phase02 runs Gemini OCR, configured object detection, and project-generated SigLIP/BEiT3 embeddings. It does not create canonical captions or scene summaries. |
| Object/concept generation | `objects`, `text_documents` | Generate on project keyframes and preserve label, score, optional box, source, and exact model/version. |
| Embedding generation | separate SigLIP and BEiT3 FAISS indexes + shared `vector_map` | Use separate `index_name` values/files and resolve every row through SQLite before returning results. |
| Validation | validation report and failure status | App-ready build is usable only when required checks pass. |

Notebook 01 / phase01 workers should reuse phase00 probe facts from
`tables/videos.parquet`, `raw_mapping/media_store_manifest.parquet`, and
`frame_timeline/{video_id}.parquet`. Phase01 may verify or stage
the current video when needed, but it should not re-probe every video or copy
the full raw dataset into worker runtime storage. A missing decoded timeline
fails that production video rather than silently deriving exact frame IDs in
notebook code. Explicit estimated/degraded mapping remains debug/test-only.

Scene grouping runs only after shots, representative/optional
early/late/supplemental keyframes, canonical shot captions, ASR segments, and
shot-transcript links
exist. It writes `scenes.parquet`, backfills `shots.scene_id` and
`keyframes.scene_id`, then builds scene-transcript links and bilingual scene
summaries. OCR, objects, and embeddings remain Phase02 outputs and are not
canonical scene-grouping inputs. The complete Phase01 production contract is
`docs/architecture/system1-notebook01-production-pipeline.md`.

## CLI Contract

Preprocessing must be runnable from batch CLI scripts. Minimum interface:

```text
aic-prepare build \
  --dataset-id aic2026 \
  --raw-video-dir ${AIC_DATA_ROOT}/raw/videos \
  --metadata-dir ${AIC_DATA_ROOT}/raw/metadata \
  --data-root ${AIC_DATA_ROOT} \
  --runtime-root ${AIC_RUNTIME_ROOT} \
  --report ${AIC_DATA_ROOT}/staging/reports/aic2026-validation.json
```

CLI rules:

- Accept input roots and output roots as config or flags.
- Treat the raw video stem as canonical `video_id` after uniqueness validation.
- Do not accept organizer keyframe/object/CLIP/map/media-info roots as
  production evidence inputs.
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
${AIC_DATA_ROOT}/raw/metadata/{video_id}.json
${AIC_DATA_ROOT}/processed/media/keyframes/{video_id}/{video_id}_f{frame_id:07d}.jpg
${AIC_DATA_ROOT}/processed/media/thumbnails/{video_id}/{video_id}_f{frame_id:07d}.webp
${AIC_DATA_ROOT}/staging/frame_timeline/{video_id}.parquet
${AIC_DATA_ROOT}/staging/staging.duckdb
${AIC_DATA_ROOT}/staging/reports/{dataset_id}-validation.json
${AIC_RUNTIME_ROOT}/db/app.sqlite
${AIC_RUNTIME_ROOT}/indexes/siglip.faiss
${AIC_RUNTIME_ROOT}/indexes/beit3.faiss
${AIC_RUNTIME_ROOT}/indexes/vector_map.parquet
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
- `canonical_metadata_path` for the required canonical JSON
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

For production Phase00 inventory, `frame_count` comes from the required decoded
timeline row count. `ffprobe -count_packets` / `nb_read_packets`, header
`nb_frames`, and duration/FPS math remain compatibility diagnostics. They do not
replace the decoded frame timeline required by production Notebook 01.

Canonical HF ingest consumes that inventory by default and does not download
`raw_videos/*.mp4` solely to repeat media probing or timeline decoding.
Notebook 00B/00C generate the decoded timeline while the video is already in
bounded stream scratch. Production HF ingest downloads and validates the
compact raw timeline Parquet and copies it into Phase00. Inventory facts without
that matching Parquet do not satisfy the Notebook 01 exact-frame contract.

Raw upload retries `ffprobe` at most three times. After exhausted retries,
unknown technical values remain nullable and the inventory/canonical JSON carry
matching `probe_status` and `probe_attempts`; HF ingest rejects any drift
between the two records.

## Hugging Face Shared Storage Contract

System 1 uses exactly two Hugging Face Dataset repos for shared state:

```text
AIC26_raw
AIC26_release
```

`AIC26_raw` is the canonical raw dataset repo. It contains standardized raw
videos, one canonical metadata JSON and one decoded timeline per video, plus
raw-level import/inventory manifests:

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

The Phase00 `media_store_manifest.parquet` retains normalized canonical video,
metadata, and frame-timeline paths plus the canonical raw prefix. This keeps
the raw provenance complete while `frame_timeline_manifest.parquet` separately
records Phase00 timeline availability and row counts.

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
organizer-metadata pairs into local scratch, probes each local video, creates
and validates its canonical metadata JSON and decoded timeline Parquet, uploads
each batch to `AIC26_raw`, records per-video progress, and cleans the scratch
batch before moving on. It does not materialize a full standardized raw tree on
Drive.

The streaming path exposes the same disk-safe option family as archive
standardization: `--min-free-gb`, `--drive-sync-sleep-seconds`,
`--cleanup-every-files`, and `--cleanup-every-gb`. Notebook 00B uses these
options to keep local scratch bounded while preserving batched Hugging Face
commits.

Notebook 00C uses the same streaming path for local laptop/workstation runs.
The source is a local downloaded zip folder, so the notebook skips Google Drive
mount/remount and `drive-shadow`, then continues with HF raw upload, canonical
HF ingest, batch assignment, and `phase00_ingestion` sync.

Phase00 sync is an exact-prefix reconciliation. It compares SHA-256 plus size
against the previous complete manifest, skips unchanged files, batches add and
delete operations with bounded transient retries, deletes stale files only
inside `<release_id>/phase00_ingestion/`, and uploads
`reports/phase00_sync_manifest.json` last. A missing completion marker means the
remote snapshot must not be treated as complete.

## Validation Gate

System 1 must prove:

- No duplicate `video_id` and no duplicate `(video_id, frame_id)`.
- Every raw video has a unique canonical `video_id` derived from its filename
  stem.
- Every raw video has one schema-valid `metadata/{video_id}.json`.
- Organizer JSON, when present in source storage, matches exactly one video,
  sets `organizer_metadata_present=true`, and contributes a source
  reference/checksum when available without being copied to a second HF tree.
- Missing organizer metadata is audited before canonical generation; its
  canonical organizer fields are null/empty and it remains a valid video.
- Canonical metadata and inventory provenance/probe fields agree.
- Organizer keyframe, object, CLIP, map-keyframes, and media-info artifacts are
  not imported into the release.
- Every video has probed fps; non-25 fps is reported against the planning/default expected value until current-year FPS is confirmed.
- Every `keyframe_id` matches `"{video_id}:{frame_id}"`.
- Every `video_ref`, `keyframe_ref`, and `thumbnail_ref` resolves through `MediaStorePort`.
- Production `frame_id` always uses the decoded original frame index; estimated
  `timestamp * fps` mapping is debug-only and cannot pass production release
  validation.
- Runtime SQLite includes `vector_map`, `feature_availability`, and enough logical refs for System 2 inspection flows.
- Every keyframe has a thumbnail ref.
- Every FAISS vector has a `vector_map` row.
- Every `vector_map.keyframe_id` exists in `keyframes`.
- Caption, OCR, and object rows point to existing keyframes.
- ASR rows point to existing videos and valid time ranges.
- SQLite contains no absolute or machine-specific paths.
- FTS5 row counts match source relational tables or documented expectations.
