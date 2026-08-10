# ADR 0016: Canonical Metadata For Every Video

Date: 2026-08-10

## Status

Accepted

## Context

The organizer provides YouTube metadata for some videos. The observed metadata
shape contains `author`, `channel_id`, `channel_url`, `description`, `keywords`,
`length`, `publish_date`, `thumbnail_url`, `title`, and `watch_url`. Other videos
may have no organizer metadata at all.

Notebook 00B and Notebook 00C are the current large-dataset ingestion paths.
Both already have each video in bounded local scratch before raw upload, which
is the correct point to probe media facts and construct one stable metadata
contract. Requiring downstream stages to handle an absent metadata file would
duplicate branching logic and can make a generated placeholder look like
organizer-provided evidence.

## Decision

Organizer metadata remains optional evidence, but canonical project metadata is
required for every canonical raw video. Before upload, Notebook 00B/00C package
code must:

1. derive `video_id` from the video filename stem;
2. read organizer JSON when it exists and record its source reference and
   checksum when available;
3. probe the video with `ffprobe`;
4. create `metadata/{video_id}.json` using one versioned canonical schema;
5. validate the canonical JSON and inventory projection; and
6. upload the video, canonical metadata, and raw audit manifests.

The canonical JSON always contains:

```json
{
  "schema_version": "1.0",
  "video_id": "L21_V001",
  "organizer_metadata_present": true,
  "author": "60 Giay Official",
  "channel_id": "UCRjzfa1E0gA50lvDQipbDMg",
  "channel_url": "https://www.youtube.com/channel/...",
  "description": "...",
  "keywords": ["..."],
  "length": 1262,
  "publish_date": "2024-08-01",
  "thumbnail_url": "https://i.ytimg.com/...",
  "title": "...",
  "watch_url": "https://youtube.com/watch?v=...",
  "media": {
    "filename": "L21_V001.mp4",
    "file_size_bytes": 130322332,
    "duration_sec": 1261.726,
    "fps": 25.0,
    "frame_count": 31543,
    "width": 1920,
    "height": 1080,
    "is_vfr": false,
    "probe_status": "pass",
    "probe_attempts": 1
  },
  "provenance": {
    "organizer_metadata_source_ref": "source-archive.zip::metadata/L21_V001.json",
    "organizer_metadata_sha256": "8b7f6e5d4c3b2a190817263544332211ffeeddccbbaa99887766554433221100",
    "technical_metadata_source": "ffprobe",
    "metadata_generated": false
  }
}
```

All organizer fields are present in every canonical JSON. Unknown scalar
values use JSON `null`; `keywords` uses an empty array. The package must not use
`video_id` as a fabricated title or use a ZIP/source path as `watch_url`.
`publish_date` is normalized to ISO `YYYY-MM-DD`. The canonical HF raw prefix
does not copy the organizer JSON into a second metadata tree. The original
archive/file remains in operator-retained source storage; provenance keeps its
source reference and checksum when available. Both provenance values are
`null` when no organizer metadata exists.

The package makes at most three `ffprobe` attempts per video, with 0.5-second
and 1-second delays before the second and third attempts. A complete result is
`probe_status="pass"`. If all retries are exhausted, canonical generation still
continues with unavailable technical fields set to `null` and
`probe_status="partial"` or `"failed"`; `probe_attempts` records the attempts.
This keeps the video ingestible while making degraded probe evidence explicit.

Organizer `length` and probed `media.duration_sec` remain separate because the
organizer value is integer seconds while `ffprobe` may provide a more precise
duration. `canonical_video_inventory.parquet` is a batch-friendly projection of
the same generated record, not an independent metadata interpretation. It has
one row per video, an always-present `canonical_metadata_path`, and explicit
`organizer_metadata_present` and `metadata_generated` columns.

`missing_metadata.json` records which videos lacked organizer metadata before
canonical metadata generation. Creating canonical JSON must not erase or
recompute that audit as zero. `unmatched_metadata.json` continues to record
organizer JSON with no matching video.

For backward compatibility, `metadata_generated=true` means organizer metadata
was absent and the canonical organizer-field section was filled with null/empty
values. The canonical JSON is still generated for every video, including rows
where `metadata_generated=false`.

Decoded frame timelines remain separate Phase00 artifacts. Inventory probe
facts do not satisfy the production exact-frame contract. Canonical HF ingest
may stage one video at a time to build the decoded timeline and must clean the
bounded stage afterward; this is distinct from downloading the full raw dataset
or downloading videos only to repeat inventory probing.

## Alternatives Considered

1. Keep organizer metadata optional at the file level. Rejected because every
   downstream stage would retain missing-file branches and inconsistent shapes.
2. Generate the current minimal placeholder. Rejected because fabricated
   `title` and `watch_url` values can be mistaken for organizer evidence.
3. Store only probed inventory rows. Rejected because per-video metadata is the
   stable handoff for structure and feature workers, while the inventory is for
   efficient bulk discovery.
4. Decode the complete frame timeline during raw upload. Rejected as a required
   metadata operation because it makes raw upload unnecessarily expensive;
   Phase00 owns decoded timeline production.

## Consequences

Positive:

- Every worker receives one predictable metadata shape per video.
- Organizer absence remains explicit and auditable.
- Technical facts and organizer values retain distinct provenance.
- Notebook 00B and 00C keep their bounded streaming behavior.

Tradeoffs:

- Raw storage includes only one small canonical JSON per video, without a
  duplicate `organizer_metadata/` tree.
- Exact re-normalization still depends on retaining the original organizer
  archive/file in source storage; the canonical record keeps its reference and
  checksum when available.
- Upload, HF ingest, schemas, tests, and notebook validation gates must migrate
  together.
- Existing raw prefixes remain historical snapshots and are not silently
  rewritten.

## Follow-Up

- The canonical builder is implemented in both raw upload paths, and canonical
  HF ingest validates the JSON against its inventory projection.
- Metadata provenance is propagated through HF ingest and Phase00 tables.
- Notebook 00B/00C validation cells enforce schema version 1.0 without moving
  business logic into the notebooks.
- Implement bounded Phase00 decoded-timeline staging for production runs.
