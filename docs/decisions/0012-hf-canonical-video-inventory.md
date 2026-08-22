# ADR 0012: HF Canonical Video Inventory

Date: 2026-06-27

## Status

Accepted

Amended by ADR 0016 on 2026-08-10: canonical metadata now exists for every
video, the inventory carries metadata provenance and additional media facts,
and bounded video staging is allowed during raw upload. Amended by ADR 0017 on
2026-08-11: production timelines are built in that existing raw-upload scratch
and canonical HF ingest reuses the compact Parquet. The prohibition below
remains specific to downloading videos only to repeat inventory probing or
timeline decoding.

## Context

The raw canonical Hugging Face Dataset stores large source videos. HF canonical
ingest previously downloaded each raw video again to probe duration, FPS, and
frame count, which can fill a Colab runtime disk through Hugging Face cache and
staging copies.

## Decision

`upload-standardized-raw` writes
`<raw_import_id>/manifests/canonical_video_inventory.parquet` while local videos
are still available. HF canonical ingest reads that small inventory and uses it
for per-video duration, FPS, frame count, source file size, and canonical path
metadata. The inventory includes:

- `video_id`
- `canonical_repo_id`
- `canonical_repo_type`
- `canonical_revision`
- `canonical_prefix`
- `canonical_video_path`
- `canonical_metadata_path`
- `canonical_frame_timeline_path`
- `frame_timeline_status`
- `frame_timeline_row_count`
- `frame_timeline_size_bytes`
- `organizer_metadata_present`
- `metadata_generated`
- `duration_sec`
- `fps`
- `frame_count`
- `width`
- `height`
- `is_vfr`
- `file_size_bytes`

By default, HF canonical ingest must not download `raw_videos/*.mp4` only for
probing or timeline decoding. Production raw upload builds the timeline while
the video is already in bounded scratch, and HF ingest validates the compact
Parquet. The legacy inventory download/probe fallback is allowed only when
`AIC_ALLOW_HF_VIDEO_DOWNLOAD_FOR_PROBE=1` is set.

## Alternatives Considered

1. Continue downloading raw videos from HF during ingest. Rejected because it
   duplicates I/O and can exhaust Colab runtime disk through cache growth.
2. Store probe fields only in `canonical_file_manifest.jsonl`. Deferred to
   avoid changing that manifest schema during this task.
3. Skip probing in canonical upload and accept missing timing fields. Rejected
   because downstream ingestion still needs per-video FPS, duration, and frame
   count.

## Consequences

Positive:

- HF canonical ingest reads a small Parquet inventory instead of re-downloading
  large videos by default.
- Per-video FPS, duration, frame count, and file size remain available in
  `videos.parquet` and media mapping outputs.
- Existing raw-video download behavior remains available for controlled debug
  fallback through an explicit environment variable.

Tradeoffs:

- Raw canonical uploads now require probing local videos before writing the
  inventory.
- Raw repos created before this ADR must be regenerated or ingested with the
  explicit fallback environment variable.

## Follow-Up

- Implement and validate the ADR 0016 inventory additions together with the
  canonical metadata builder and Phase00 provenance propagation.
