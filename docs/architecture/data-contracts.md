# Data Contract

## Status

Canonical for Phase00 ingest and for the System 1 worker package, caption
package, and runtime release (`release_v2`). Rewritten 2026-10-26 under
ADR 0021 to 0026 and `docs/plans/active/system1-pipeline-simplification.md`
Step 5d. Query-session and agent-state tables moved to
`docs/architecture/system2-retrieval.md`; they are runtime state, not release
content.

Machine-readable schemas: `system1/schemas/v2/*.schema.json`, one per table.
A change to a table changes this document, its schema file, and the validating
test together. Schemas under `system1/schemas/*.schema.json` (no `v2`) belong
to the pre-ADR-0021 pipeline and are removed in plan Step 6.

See also: `docs/architecture/system1-target.md` (pipeline and stage behavior),
`docs/architecture/storage-strategy.md`.

## Principle

Runtime code must not infer dataset structure from raw files. System 1 turns
organizer inputs into the release below; System 2 reads only the release.

| Layer | Role |
| --- | --- |
| Parquet, JSON | Phase00 inventories, worker and caption package tables, release staging |
| SQLite (WAL) + FTS5 | Runtime catalog and text search inside `db/app.sqlite` |
| FAISS | Runtime vector indexes, one file per index, inner product over L2-normalized vectors |
| Files | Videos, keyframes, thumbnails |

Never fabricate data: a missing organizer field is `null`, a failed stage is
recorded in the package manifest, and a missing caption is a missing row.

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

| Root | Purpose |
| --- | --- |
| `${REPO_ROOT}` | Source, docs, config, schemas, small fixtures. No competition media. |
| `${AIC_DATA_ROOT}` | Large data on the System 2 host: the synced release (`releases/{release_id}/`) and, optionally, raw videos. |
| `${AIC_RUNTIME_ROOT}` | Hot runtime files on SSD when they are copied out of the release: `db/app.sqlite`, `indexes/`. Optional; a release is usable in place. |

## Storage Layout

Three layers, three write policies (ADR 0025).

```text
Hugging Face dataset repo 1thesudden/AIOU26_raw          written once by Phase00
  canonical_raw_v001/raw_videos/{video_id}.mp4
  canonical_raw_v001/metadata/{video_id}.json
  canonical_raw_v001/frame_timeline/{video_id}.parquet
  canonical_raw_v001/manifests/                          inventory and import reports (section below)

Hugging Face dataset repo 1thesudden/AIOU26_release      immutable packages, Git history kept
  {release_id}/phase00_ingestion/manifests/{batch_id}.txt
  {release_id}/phase00_ingestion/raw_mapping/media_store_manifest.parquet
  {release_id}/phase00_ingestion/tables/videos.parquet
  {release_id}/worker/artifacts/{batch_id}/{video_id}.zip
  {release_id}/worker/reports/{batch_id}_{worker_id}.json
  {release_id}/captions/artifacts/{batch_id}/{video_id}.zip
  {release_id}/captions/reports/{batch_id}_{worker_id}.json

Hugging Face Storage Bucket 1thesudden/aiou-app-storage  rebuilt and overwritten
  releases/{release_id}/                                 runtime release (section below)
```

Test runs write to `1thesudden/AIOU26_release_test` and to the bucket prefix
`releases_test/`. Production prefixes are never written by a test run.

`release_id` is `canonical_release_v001` for Batch 1. A Phase00 batch manifest
lists about 73 `video_id`s per line-separated file; worker and caption passes
run one batch per Kaggle session.

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

## Canonical IDs

Formats are listed under Tables, Identifiers. Rules:

- `video_id` is the raw video filename stem, never derived from `watch_url`.
- `frame_id` is the decoded frame index from the Phase00 frame timeline
  (ADR 0017), never `time * fps`. Batch 1 videos are 25 fps; that is an
  expectation to check, not a constant to use.
- `video_id + frame_id` is the submission unit; `keyframe_id` is the join key.

## Logical Media References

Tables store logical refs only, never absolute or machine-specific paths.

| Asset | Pattern | Where |
| --- | --- | --- |
| Video | `raw_videos/{video_id}.mp4` | `AIOU26_raw/canonical_raw_v001/` |
| Keyframe (worker package) | `keyframes/{video_id}/{video_id}_f{frame_id:07d}.jpg` | inside the worker ZIP; JPEG quality 90, long side 1280 |
| Keyframe (runtime release) | `keyframes/{video_id}/{video_id}_f{frame_id:07d}.webp` | `media/` in the release; WebP quality 80, same resolution (ADR 0025) |
| Thumbnail | `thumbnails/{video_id}/{video_id}_f{frame_id:07d}.webp` | both; WebP, width 320 |

Models (SigLIP2, OCR, captions) read the worker-package JPEG. The release WebP
is for display only. System 2 resolves refs against the synced release root.

## Worker Package

One ZIP per video, written by `worker-batch`, validated by
`system1.worker.package.validate_package`, immutable once uploaded.

```text
{video_id}.zip
  {video_id}/
    manifest.json             worker_package_v2: video_id, config_schema_version,
                              models (id and revision per stage), stages (status,
                              counts, seconds per stage)
    artifact_manifest.json    file list with sizes
    checksums.json            sha256 per file
    cut_segments.parquet      cut_segments_v1
    shots.parquet             shots_v2 (scene_id null)
    keyframes.parquet         keyframes_v4
    image_vectors.npy         float32 [n_keyframes, 1152], L2-normalized, row i = keyframes row i
    asr_segments.parquet      asr_segments_v2
    ocr.parquet               ocr_v2
    text_documents.parquet    text_documents_v2, evidence_type in {asr, ocr}
    text_vectors.npy          float32 [n_documents, 1024], L2-normalized, row i = text_documents row i
    keyframes/{video_id}/*.jpg
    thumbnails/{video_id}/*.webp
```

Stage statuses in `manifest.json`: `pass`, `empty`, `failed`, `fallback`,
`skipped`. `cuts`, `keyframes`, and `image_vectors` must be `pass` or
`fallback`; `asr` and `ocr` may be `empty` or `failed` and the package is still
valid (ADR 0024). A package with `failed` or `fallback` stages is reprocessed
on the next worker run of that batch.

## Caption Package

One ZIP per video, written by `caption-batch` from a worker package (ADR 0025).

```text
{video_id}.zip
  {video_id}/
    manifest.json             caption_package_v1: video_id, worker_package_sha256,
                              model id and revision, stage report (captions,
                              rejected, seconds)
    checksums.json
    captions.parquet          captions_v2, one row per shot
    text_documents.parquet    text_documents_v2, evidence_type in {caption, visible_text}
    text_vectors.npy          float32 [n_documents, 1024]
```

`worker_package_sha256` ties the caption package to the exact worker package
it was built from; `build-release` rejects a mismatch.

## Tables

Column lists are authoritative in `system1/schemas/v2/`. This section states
the rules the schemas cannot express.

### Identifiers

| ID | Format | Example |
| --- | --- | --- |
| `video_id` | organizer file stem | `L21_V014` |
| `frame_id` | decoded frame index from the Phase00 frame timeline (ADR 0017) | `25300` |
| `keyframe_id` | `{video_id}:{frame_id}` | `L21_V014:25300` |
| `cut_segment_id` | `{video_id}_CS{n:05d}`, n from 0 in time order | `L21_V014_CS00012` |
| `shot_id` | `{video_id}_SH{n:05d}`, n from 0 in time order | `L21_V014_SH00034` |
| `scene_id` | `{video_id}_SC{n:05d}`, n from 0 in time order | `L21_V014_SC00007` |
| `doc_id` | `{video_id}:{evidence_type}:{n:05d}` | `L21_V014:asr:00003` |
| `vector_id` | FAISS row, integer from 0 | `4711` |

`video_id + frame_id` is the submission unit. All frame ranges are
`[start_frame, end_frame)`; `timestamp_sec` and `start_sec`/`end_sec` are the
decoded `pts_time` of those frames.

### Structure

- `cut_segments` tile the video's frames. A failed or cut-free detection
  yields one segment over all frames.
- `shots` tile their `cut_segment`; a shot never crosses a cut. A shot is a run
  of near-identical frames (ADR 0022); `scene_id` is null in worker packages
  and set in the release.
- `keyframes`: every shot has at least one keyframe (`selection_reason
  shot_start`) and exactly one `is_representative = true`; extra keyframes
  inside a shot have `selection_reason visual_change`. Every keyframe lies in
  its shot's frame range.
- `scenes` (release only, ADR 0026) tile the video's shots in order;
  `start_frame`/`end_frame` equal the first and last shot's bounds.
  `summary` is the scene's distinct shot captions joined in time order, null
  when no shot has a caption (ADR 0026 amendment 2026-10-26).

### Evidence

- `asr_segments`: raw ChunkFormer segments; may be empty.
- `ocr`: one row per keyframe, `lines` may be empty.
- `captions` (caption package): one row per shot. A row whose `problems` is
  non-empty has no caption or `visible_text` document.
- `text_documents` is the only text-search table. `evidence_type`:
  `asr` (10 to 30 s chunks), `ocr` (one keyframe's lines joined by newline),
  `caption`, `visible_text`, `scene` (release only). `shot_ids` lists the shots
  overlapping `[start_sec, end_sec]`. `keyframe_id` is set for `ocr`,
  `caption`, `visible_text` and null otherwise. `text_unaccented` is `text`
  with Vietnamese diacritics removed (`system1.text.evidence.unaccent`).
  Every row has a text vector at the same index.
- `window` (boolean, required) is true for overlapping `asr` windows
  (`text.asr_window_sec` long, stepped by `text.asr_window_step_sec`) and
  false for every other row, including `asr` chunks. Chunks cut at sentence
  punctuation or a pause longer than `text.asr_sentence_gap_sec` when one
  exists. Window `doc_id`s continue the `asr` numbering after the chunks.
  Release FTS and vectors index window rows like other rows; System 2 dedupes
  hits on `window`.

### Vectors

| Index | Vectors | Dim | Items |
| --- | --- | --- | --- |
| `image_siglip2` | SigLIP2 so400m-patch14-384 image embeddings | 1152 | `keyframe_id` |
| `text_e5` | multilingual-e5-large passage embeddings (`passage: ` prefix) | 1024 | `doc_id` |

Vectors are L2-normalized; indexes are `IndexFlatIP`. Query text uses
SigLIP2's text tower for `image_siglip2` and E5 with the `query: ` prefix for
`text_e5`.

`vector_map` holds `(index_name, vector_id, item_id)`. It is stored twice with
identical rows: `indexes/{index_name}_vector_map.parquet` beside each index,
and the SQLite table `vector_map`. The release validator checks they agree and
that every `item_id` exists.

## Runtime Release

Written by `build-release`, uploaded by `publish-release` to the bucket prefix
`releases/{release_id}/` (ADR 0025). The release is the only input System 2
needs.

```text
releases/{release_id}/
  manifest.json                 release_v2: release_id, built_at, videos,
                                videos_with_captions, models, counts per table,
                                vectors per index, degraded_stages per video,
                                schema files and their sha256
  db/app.sqlite                 tables below + text_documents_fts + vector_map
  indexes/image_siglip2.faiss
  indexes/image_siglip2_vector_map.parquet
  indexes/text_e5.faiss
  indexes/text_e5_vector_map.parquet
  media/keyframes/{video_id}/{video_id}_f{frame_id:07d}.webp
  media/thumbnails/{video_id}/{video_id}_f{frame_id:07d}.webp
  READY.json                    written last: release_id, manifest sha256, file count
```

A reader treats a prefix without `READY.json` as incomplete.

### SQLite tables

| Table | Schema | Rows |
| --- | --- | --- |
| `videos` | `videos_v2` | one per video, from Phase00 canonical metadata and frame timeline |
| `cut_segments` | `cut_segments_v1` | merged from packages |
| `shots` | `shots_v2` | merged; `scene_id` set |
| `scenes` | `scenes_v2` | built at release time (ADR 0026) |
| `keyframes` | `keyframes_v4` | merged; `keyframe_ref` ends in `.webp` |
| `text_documents` | `text_documents_v2` | merged worker and caption documents plus `scene` summaries |
| `text_documents_fts` | FTS5 over `text`, `text_unaccented`; `tokenize='unicode61 remove_diacritics 0'`; external content table `text_documents` | one per document |
| `vector_map` | `vector_map_v2` | one per FAISS row |

Indexes: unique on `videos.video_id`, `shots.shot_id`, `scenes.scene_id`,
`keyframes.keyframe_id`, `text_documents.doc_id`, `vector_map(index_name,
vector_id)`; non-unique on `keyframes(video_id, timestamp_sec)`,
`text_documents(video_id, start_sec)`, `shots(video_id, start_sec)`.

`asr_segments`, `ocr`, and `captions` are not release tables; their content
reaches System 2 through `text_documents`. Required pragmas:
`journal_mode=WAL`, `foreign_keys=ON`.

### Resolution flow

```text
FAISS vector_id → vector_map → keyframe_id or doc_id
keyframe_id → keyframes (video_id, frame_id, shot_id, timestamp_sec, refs)
doc_id → text_documents (video_id, start_sec, end_sec, shot_ids, keyframe_id)
shot_id → shots → scene_id → scenes
video_id → videos (duration_sec, fps for the temporal window)
```

## Validation

`validate_package` (worker and caption packages) and `build-release` fail on:

- a table row that violates its `v2` schema;
- a file in `checksums.json` whose sha256 differs;
- rows of another `video_id` inside a package;
- `keyframe_id` not equal to `{video_id}:{frame_id}`; duplicate `keyframe_id`
  or `doc_id`;
- a shot outside its cut segment, a keyframe outside its shot, a shot without
  exactly one representative keyframe;
- a vector file whose row count differs from its table, or a non-finite or
  non-normalized vector;
- a `keyframe_ref` or `thumbnail_ref` without a file;
- in the release: a caption package whose `worker_package_sha256` differs from
  the worker package; scenes that do not tile the shots; `vector_map` Parquet
  and SQLite rows that differ; a `vector_map.item_id` without a row; a
  `shots.scene_id` without a scene; FTS row count different from
  `text_documents`.

Degraded stages (`asr`, `ocr` empty or failed; missing caption package) do not
fail validation. They are listed in `manifest.json` under `degraded_stages`.

## Test Fixtures

`system1/tests/test_worker_video.py` builds a synthetic video and fake models
and produces a complete worker package; `test_release_build.py` builds a
release from such packages. These fixtures are the seed dataset; no checked-in
media is needed.

## Open Items

- Official Batch 2 dataset structure and final submission transport are not
  confirmed.
- `scenes`, `scene` documents, `is_representative`, and `videos` are specified
  here and in `schemas/v2/` ahead of the code that writes them (plan Step 5b
  and 5d). Until that code lands, worker packages carry `worker_package_v1`
  manifests without `scene_id` and `is_representative`.
