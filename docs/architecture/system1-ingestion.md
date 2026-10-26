# System 1: Phase00 Ingestion

## Status

Live for Phase00 (ingest, canonical metadata, decoded frame timeline, batch
assignment). Phase01 and the release step are described in
`docs/architecture/system1-target.md`; tables and IDs in
`docs/architecture/data-contracts.md`. Pre-2026-10-26 Phase01/Phase02 content
of this file is in `docs/archive/system1-ingestion-phase01-02.md`.

## Responsibility

Phase00 turns organizer videos plus optional organizer metadata into one
canonical video, one canonical metadata JSON, and one decoded frame timeline
per video, then writes the `videos` table and batch manifests that the worker
(`worker-batch`) reads. CLI commands: `stream-standardize-upload-raw`,
`upload-standardized-raw`, `import-canonical-raw`, `ingest`,
`assign-batches`, `sync-phase00-ingestion`, `restore-phase00-ingestion`.
Notebooks: `00B_master_ingestion_and_assignment.ipynb` (Colab) and
`00C_master_ingestion_local.ipynb` (local).

## Stages

| Stage | Required Output | Notes |
| --- | --- | --- |
| Dataset registration | `datasets` row and build manifest | Assign stable `dataset_id`, source version, build time, and source roots. |
| Dataset mapping | input manifest | Use the raw video filename stem as `video_id`; fail on duplicate video stems; record missing organizer metadata before canonical metadata generation. |
| Media discovery | `videos`, discovered media manifest | Discover videos from configurable roots; do not hardcode personal paths or filename regexes. |
| Metadata normalization | `metadata/{video_id}.json` and normalized staging fields | Create one versioned canonical JSON per video. Normalize the ten observed organizer fields, retain source reference/checksum when available, use null/empty values when absent, and attach `ffprobe` media facts and provenance. Do not upload a duplicate organizer metadata tree. Missing organizer metadata must not remove the video. |
| Video probing | probed media facts | Probe fps, duration, dimensions, codec/container facts; last-year evidence suggests 25 fps, but actual fps must be persisted per video. |
| Timeline mapping | `frame_timeline` staging rows or equivalent mapping proof | Persist enough timing metadata to map timestamps to frame ids safely, especially for VFR or unreliable FPS metadata. |

The worker reuses Phase00 facts from `tables/videos.parquet`,
`raw_mapping/media_store_manifest.parquet`, and
`frame_timeline/{video_id}.parquet`. A missing decoded timeline fails that
video.

## Raw Inventory

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

## Hugging Face Storage

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

Worker, caption, and release storage are described in
`docs/architecture/system1-target.md` (Hugging Face Layout) and ADR 0025.

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

Phase00 must prove:

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
