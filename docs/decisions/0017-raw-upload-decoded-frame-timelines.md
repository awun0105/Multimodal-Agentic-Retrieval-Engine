# ADR 0017: Build Decoded Timelines During Canonical Raw Upload

Date: 2026-08-11

## Status

Accepted

## Context

Production Notebook 01 requires an exact decoded mapping from `frame_id` to
presentation time. Canonical metadata and packet/header counts cannot replace
that mapping. Notebook 00B/00C already extract each source video into bounded
local scratch for raw upload. Building timelines later during canonical HF
ingest would download and scan the same large video again, increasing network,
disk, and runtime cost.

## Decision

Notebook 00B/00C package code builds and validates
`frame_timeline/{video_id}.parquet` while each video is already in raw-upload
scratch. A production run uses `frame_timeline_policy=required` and fails the
video after three bounded attempts if the timeline cannot be created.

The canonical raw manifest, inventory, report, and progress record carry the
timeline path, status, row count, size, and upload status. A successful required
resume row is complete only when the remote timeline still exists; older passes
without it are re-extracted to backfill the timeline without re-uploading
existing video or metadata files.

Canonical HF ingest downloads and validates the compact timeline Parquet and
materializes it into Phase00. It does not download the MP4 to repeat timeline
decoding. Compatibility/debug callers may explicitly choose `if-available` or
`disabled`; those policies do not satisfy the production Notebook 01 gate.

Timeline probing performs one lightweight stream-header query and one decoded
frame scan. Because decoded rows supply the authoritative frame count, it avoids
a redundant full `ffprobe -count_packets` scan.

The package streams decoded rows into one Parquet file per video in bounded
8,192-row chunks. It writes a `.partial` file, validates row IDs, timestamps,
schema, and row count while building it, then atomically renames the completed
file. Chunking is an internal memory bound; it does not split a video's public
timeline contract.

Notebook 00B/00C expose `timeline_workers=auto`. The package resolves this to
one or two workers from the available CPU count and never exceeds two concurrent
`ffprobe` processes. The coordinator alone extracts zip members, writes progress,
cleans scratch, and performs batched HF commits. A worker group finishes before
upload starts, so there are no concurrent HF commits or upload/probe contention.
Operators can force `1` for constrained runtimes or `2` after a small pilot.

The authoritative timeline lives under
`AIC26_raw/<raw_import_id>/frame_timeline/`. Canonical ingest copies the validated
artifact into `AIC26_release/<release_id>/phase00_ingestion/frame_timeline/` as a
Phase00 worker snapshot; it does not regenerate the timeline.

## Alternatives Considered

1. Decode timelines during canonical HF ingest. Rejected because it downloads
   and scans every large video again after raw upload.
2. Use packet count, header count, or timestamp-times-FPS mapping. Rejected for
   production because those facts do not prove exact decoded frame IDs,
   especially for VFR or malformed media.
3. Make timelines optional in Notebook 00B/00C. Retained only as an explicit
   compatibility/debug policy; production requires the artifact.

## Consequences

Positive:

- Each source video is transferred to HF once and receives metadata plus exact
  frame mapping in the same bounded scratch lifecycle.
- Canonical HF ingest transfers only small metadata/timeline artifacts.
- Notebook 01 can fail early and clearly when exact mapping is unavailable.
- Streaming Parquet bounds Python memory, while the two-worker cap improves
  Colab throughput without parallel HF commits.

Tradeoffs:

- Raw upload performs a full decoded-frame scan before upload.
- Existing raw prefixes without timelines must be backfilled or replaced with a
  new versioned prefix before production ingest.
- The raw repo contains an additional Parquet file per video.
- Two simultaneous scans can compete for CPU or local disk on a constrained
  runtime; `timeline_workers=1` remains the deterministic fallback.

## Validation

- Unit tests cover retry, schema, contiguous frame IDs, monotonic PTS, and file
  validation.
- Integration tests cover both raw upload paths, required resume backfill,
  bounded worker concurrency, upload/probe separation, canonical HF ingest
  without MP4 download, and Notebook 01 enforcement.
- A real sample timeline produced 31,720 rows identical to the previous
  in-memory implementation while reducing peak process RSS.
- A live full-dataset HF rehearsal remains an operator validation step.
