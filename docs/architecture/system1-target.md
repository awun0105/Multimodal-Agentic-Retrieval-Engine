# System 1 Target Architecture

Date: 2026-10-25

## Status

Target design for `docs/plans/active/system1-pipeline-simplification.md`.
It describes System 1 after the plan completes. Each part is marked:

- **Decided**: fixed by an accepted ADR.
- **Proposed**: the plan's working design; confirm or change during
  implementation and record the result here.
- **Pending trial**: chosen after the Kaggle trials in plan Step 3.

Where this document conflicts with older System 1 architecture documents, this
document and ADRs 0021 to 0024 win. Phase00 is unchanged and remains described
by `docs/architecture/system1-ingestion.md`, ADR 0016, and ADR 0017.

## Goal

Turn official videos plus optional organizer metadata into one searchable
release for System 2: keyframes, image vectors, time-ranged text (ASR, OCR,
captions) with text vectors and full-text search, and the IDs that map every
result to `video_id` and `frame_id`.

## Pipeline Overview

```text
Organizer videos + optional metadata
  │
  ▼
Phase00  Ingest (unchanged)                          Notebook 00B/00C
  canonical video, metadata JSON, decoded frame timeline → HF AIOU26_raw
  videos table, batch manifests                     → HF AIOU26_release/phase00_ingestion
  │
  ▼
Phase01  Per-video worker                             Notebook 01 (one batch per worker)
  1 ASR              speech to text with timestamps (runs first, most GPU memory free)
  2 cuts             TransNetV2 cut segments
  3 shots, keyframes split cut segments into shots by visual change; keyframes
  4 image vectors    one vector per keyframe
  5 OCR              per keyframe, noise and logo filter
  6 captions         one constrained JSON call per shot (optional)
  7 text documents   ASR chunks (10-30 s), OCR, captions; text vectors
  8 package          per-video ZIP + output validation
  9 sync             → HF AIOU26_release/phase01/artifacts/{batch_id}/{video_id}.zip
  │
  ▼
Release  Merge, index, validate                       Notebook 02
  restore all per-video ZIPs → merge tables → SQLite + FTS5
  → FAISS image index(es) + text index → release validation → publish
  │
  ▼
Runtime contract → System 2 (search, temporal window, fusion, UI)
```

## Phase00: Ingest (Decided, unchanged)

Notebook 00B (Colab and Drive) or 00C (local) streams organizer archives,
derives `video_id` from the file stem, writes one canonical metadata JSON per
video from organizer fields plus `ffprobe`, builds the decoded frame timeline
(`frame_timeline/{video_id}.parquet`), and uploads to `AIOU26_raw`. Canonical
ingest then writes the `videos` table and batch manifests to
`AIOU26_release/{release_id}/phase00_ingestion/`.

Current data: 873 videos in `canonical_raw_v001`; Phase00 complete for
`canonical_release_v001`.

## Phase01: Per-Video Worker

One worker processes one assigned batch. Videos run one at a time; each stage
has a checkpoint so a restarted Kaggle session resumes at the first unfinished
stage of the first unfinished video.

Terms: a **shot** is a run of near-identical frames; a new shot starts at a
cut or when the content changes too much. A **cut segment** is the frame range
between two TransNetV2 cuts and may contain several shots (ADR 0022).

| # | Stage | Input | Output | Model | Status |
| --- | --- | --- | --- | --- | --- |
| 1 | Cuts | video, frame timeline | `cut_segments` | TransNetV2 | Decided (kept) |
| 2 | Shots and keyframes | video, cut segments, timeline | `shots`, `keyframes`, keyframe JPEGs, thumbnails | none (difference hash) | Decided (ADR 0022); thresholds Pending trial |
| 3 | Image vectors | keyframe JPEGs | one vector file | SigLIP2 so400m-patch14-384 | Decided (ADR 0023) |
| 4 | ASR | 16 kHz mono audio | `asr_segments` (segment timestamps), `asr_chunks` (10-30 s, mapped to shots) | ChunkFormer-large-vie | Decided (ADR 0023) |
| 5 | OCR | keyframe JPEGs | `ocr` (text per keyframe, after noise, dedup, and logo filter) | EasyOCR detection + VietOCR recognition | Decided (ADR 0023) |
| 6 | Captions | middle keyframe of each shot | `captions` (caption, objects, actions, visible_text; Vietnamese) | Qwen3-VL-4B, xgrammar constrained, batch 16, 512 px | Decided model; kept only if evaluation shows gain |
| 7 | Text vectors | caption and ASR chunk documents | one text vector file | multilingual-e5-large | Decided (ADR 0023) |
| 8 | Package | stage outputs | per-video ZIP with manifest and checksums | none | Decided (ADR 0024 validator) |
| 9 | Sync | per-video ZIP | HF upload, receipt | none | Proposed layout |

Removed from Phase01 (ADR 0021): scene grouping, scene transcript links, scene
summaries, scene review, and the scene quality guard.

### Keyframe sampling (stage 2)

1. Candidates at least every N seconds across each cut segment (N initially 1
   to 2).
2. Keep a candidate when it differs enough from the last kept keyframe.
3. Start a new shot when content drifts past a threshold or the shot reaches
   its maximum length (initially 10 to 15 seconds). Shots tile their cut
   segment without gaps.
4. No keyframe or shot crosses a TransNetV2 cut; keyframes avoid transition
   frames.
5. A cut segment with no valid candidate is skipped and logged.

A video recorded in one take therefore gets shots and keyframes across its
whole length.

### Failure behavior (ADR 0024)

- Fail the video: unreadable media, `video_id` or frame mapping errors,
  schema-invalid package, checksum mismatch.
- Continue and record: empty or failed ASR, OCR, or caption for an item; an
  invalid shot or keyframe candidate. If cut detection fails, the whole video
  is one cut segment and shots still split by visual change (status
  `fallback`). Failed and fallback stages run again on the next attempt.
- Content checks at package time: OCR or caption equal to prompt text, one
  string repeated across most keyframes, high invalid-syllable rate in ASR,
  generic captions.
- Preflight checks only credentials, write access, and required executables.

## Release Step: Merge, Index, Validate (Proposed)

Notebook 02 (replaces current Notebooks 02 and 03):

1. Restore every per-video ZIP for the release from Hugging Face.
2. Merge per-video tables into release tables.
3. Build SQLite with FTS5 over text documents, with a diacritic-free column.
4. Build FAISS inner-product index(es) over L2-normalized image vectors and one
   over text vectors, each with a vector map.
5. Validate the release (IDs, mappings, counts, schema) and publish it to
   `AIOU26_release/{release_id}/release/`.

## Runtime Contract For System 2 (Proposed)

The release is the only input System 2 needs.

```text
release/
  manifest.json                 release ID, models, counts, checksums
  db/app.sqlite
    videos                      video_id, metadata, duration, fps
    shots                       shot_id, video_id, frame and time range
    keyframes                   keyframe_id, video_id, frame_id, time_sec,
                                shot_id, cut_segment_id, image and thumbnail refs
    text_documents              doc_id, video_id, start/end time and frame,
                                shot_id, evidence_type (asr | ocr | caption),
                                text, text_unaccented
    text_documents_fts          FTS5 over text and text_unaccented
  indexes/
    image_siglip2.faiss         image index
    image_vector_map.parquet    (index_name, vector_id) → keyframe_id
    text.faiss
    text_vector_map.parquet     vector_id → doc_id
  media/keyframes/, media/thumbnails/
```

System 2 searches image vectors, text vectors, and FTS5; fuses ranked lists
with Reciprocal Rank Fusion; then applies the query-time temporal window
(ADR 0021).

## Hugging Face Layout (Proposed)

```text
AIOU26_raw/canonical_raw_v001/            unchanged (Phase00)
AIOU26_release/{release_id}/
  phase00_ingestion/                      unchanged
  phase01/artifacts/{batch_id}/{video_id}.zip
  phase01/worker_reports/
  release/                                runtime contract above
AIOU26_checkpoints/phase01_checkpoints/{release_id}/{video_id}/
```

Test runs write only to `AIOU26_release_test` and `AIOU26_checkpoints_test`.

## Open Items

| Item | Resolved by |
| --- | --- |
| Keyframe interval, dedup, and shot-split thresholds | Plan Step 3 trial and first batch |
| Keep or drop captions | Evaluation set |
| GPU time per video and total for 873 videos | Plan Step 6 run |
| Exact table columns and Parquet schemas | Implementation, with `system1/schemas/` |
