# ADR 0012: HF Canonical Video Inventory

Date: 2026-06-27

## Status

Accepted

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
- `duration_sec`
- `fps`
- `frame_count`
- `file_size_bytes`

By default, HF canonical ingest must not download `raw_videos/*.mp4` for
probing. The legacy download/probe fallback is allowed only when
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

- Consider including width and height in a future inventory version if
  downstream workflows need those fields without video download.
