# MVP-0.6 System 1 Mini Seed Dataset And Validation

## Status

planned

## Lane

normal

## Product Contract

Create the smallest executable System 1 slice that proves the app-ready data
contract can be built from real organizer-style inputs: official raw `.mp4`
videos plus optional organizer metadata mapped by `video_id`, normalized into
one canonical metadata JSON per video.

This story does not build the full competition pipeline. It creates a tiny
seed path that proves the repo can discover inputs, assign stable IDs, generate
minimal derived media, build app-ready SQLite/FTS/vector mapping fixtures, and
emit a validation report that System 2 can trust.

## Relevant Product Docs

- `docs/architecture/system1-ingestion.md`
- `docs/architecture/data-contracts.md`
- `docs/planning/implementation-phases/phase-01-system1-mini-seed-and-validation.md`
- `docs/validation/test-matrix.md`
- `docs/onboarding/system1_spec.md`

## Implementation Tickets

### Ticket 1 — Tiny Seed Dataset Layout

Goal: define a tiny seed input layout using 1-2 raw videos plus optional
metadata.

Scope:

- Choose or document the fixture location.
- Keep raw media out of the repo unless intentionally tiny.
- Record expected folder names for raw videos and metadata.

Acceptance criteria:

- Raw video and metadata roots are configurable.
- Each video fixture uses the filename stem as `video_id`.
- Duplicate video stems fail validation; unmatched metadata is reported without
  removing the video.

### Ticket 2 — Pairing And Manifest Builder

Goal: build the first System 1 manifest from raw video and metadata roots.

Scope:

- Scan raw videos.
- Scan metadata JSON files.
- Pair by filename stem.
- Assign `video_id = filename stem`.
- Emit `videos.parquet` and `media_store_manifest.parquet` or equivalent seed-friendly files.

Acceptance criteria:

- `video_id` never derives from `watch_url`, title, channel, or online ID.
- `video_ref` is the canonical raw-video logical ref.
- Runtime-facing outputs do not contain absolute machine paths.

### Ticket 3 — Media Probe And Frame Metadata

Goal: persist enough frame/FPS metadata to make frame mapping auditable.

Scope:

- Probe duration, dimensions, codec/container facts, detected FPS, and VFR indicator when available.
- Prefer packet-counted frame count (`ffprobe -count_packets` /
  `nb_read_packets`) when available.
- Emit `frame_count`, `frame_count_estimated`, `frame_count_method`, `fps_detected`, `fps_source`, `is_vfr`, and `frame_id_method`.
- Emit `manifests/frame_timeline_manifest.parquet` for every Phase00 ingest
  and `frame_timeline/{video_id}.parquet` decoded frame rows when the decoded
  timeline is available.
- Treat `decoded_frame_timeline` as the primary frame-id/timestamp mapping
  method; FPS math remains a marked fallback/degraded path.

Acceptance criteria:

- `25` is only an expected/default FPS, not a hardcoded truth.
- Fallback timestamp-to-FPS frame mapping is marked estimated/degraded when it is the only method.
- Validation catches missing required frame/FPS metadata.

### Ticket 4 — Minimal Keyframe And Thumbnail Generation

Goal: generate minimal derived media for the seed videos.

Scope:

- Generate at least one keyframe per seed video.
- Generate thumbnails or explicit placeholders with degraded status.
- Use `keyframe_id = "{video_id}:{frame_id}"`.
- Store `keyframe_ref` and `thumbnail_ref` as logical refs.

Acceptance criteria:

- Keyframe extraction in MVP stable mode depends on raw video + shots + keyframe config, not scene heuristics.
- Debug/mock fixtures may emit an explicitly non-production fallback shot;
  production TransNet V2 failures fail the video.
- `keyframe_ref` and `thumbnail_ref` resolve through the media store.

### Ticket 5 — Minimal App-ready SQLite And Vector Map Fixture

Goal: build a tiny `app.sqlite` that proves System 2 can read the contract.

Scope:

- Create runtime tables needed by the seed path: `datasets`, `videos`, `shots`, `keyframes`, `vector_map`, `feature_availability`, and minimal text/evidence tables.
- Create FTS5 tables inside `app.sqlite` from metadata text at minimum.
- Create a tiny `vector_map` fixture; FAISS may be stubbed if actual index build is out of scope for the first seed proof.

Acceptance criteria:

- `app.sqlite.vector_map` is the runtime source of truth for vector resolution.
- `vector_map` includes `index_name`, `index_version`, `embedding_model`, `vector_id`, `keyframe_id`, `video_id`, and `frame_id`.
- `feature_availability` reports pass/degraded/missing/failed status for seed entities.

### Ticket 6 — Validation Report

Goal: emit a machine-readable validation report for the seed artifact set.

Scope:

- Validate raw video/metadata pairing.
- Validate no duplicate `video_id` and no duplicate `(video_id, frame_id)`.
- Validate logical refs resolve.
- Validate SQLite contains no absolute or machine-specific paths.
- Validate `vector_map` rows resolve to keyframes.
- Validate FTS5 source rows/counts or documented expectations.

Acceptance criteria:

- Validation report has explicit pass/fail/degraded status.
- Broken fixture cases can be represented or tested.
- System 2 can reject a non-app-ready artifact set based on the report.

## Acceptance Criteria

- A tiny official-source seed dataset path exists or is documented as an operator-provided input.
- System 1 mini can build app-ready seed artifacts from raw video and optional
  organizer metadata roots while producing required canonical metadata for
  every video.
- Generated `app.sqlite` contains canonical IDs, logical refs, minimal FTS5/text evidence, `vector_map`, and `feature_availability`.
- Validation report proves video identity, refs, frame metadata, vector map, and
  SQLite path safety.
- The story leaves full dataset ingestion, advanced OCR/ASR/caption quality, and full FAISS scale to later stories.

## Design Notes

- Commands: Notebook 00's phase-based path is Drive shadow, archive
  standardization into local `raw_videos/` + `metadata/`, local ingest,
  batch assignment, then `system1 sync-phase00-ingestion` to store Notebook 00
  output under `phase00_ingestion/` in the configured Hugging Face Dataset
  repo. `system1 restore-phase00-ingestion` lets worker notebooks reload that
  output from the same repo.
- Queries: System 2 should be able to resolve `video_id/frame_id`, `keyframe_id`, and `vector_id -> keyframe_id` from `app.sqlite`.
- API: no runtime API is required in this story.
- Tables: seed path should cover `videos`, `shots`, `keyframes`, `vector_map`, `feature_availability`, and minimal FTS/text evidence tables.
- Domain rules: `video_id` is filename stem; `video_ref` is canonical raw-video logical ref; `keyframe_ref`/`thumbnail_ref` are canonical derived media refs; no absolute paths in runtime SQLite.
- UI surfaces: not applicable; System 2 UI starts after app-ready seed artifacts exist.

## Validation

When updating durable proof status, update `docs/validation/test-matrix.md` with
the focused test or runtime evidence that justifies each changed field.

| Layer | Expected proof |
| --- | --- |
| Unit | Pairing, ID, path/ref, frame metadata, and validation helper tests. |
| Integration | Build seed artifacts from tiny paired inputs and inspect `app.sqlite` plus validation report. |
| E2E | Not expected for this story. |
| Platform | Optional operator smoke command proving local build works with configured roots. |
| Release | Validation report and matrix update when implemented. |

## Repository Workflow Delta

No workflow change is required for this story. When implementation proof
changes, update `docs/validation/test-matrix.md` with the real evidence.

## Evidence

Partial phase00 implementation evidence exists for Drive archive input prep,
local phase00 ingest, and Hugging Face Dataset release sync:

- `system1 drive-shadow` copies regular Google Drive files/folders from an
  organizer folder into a user-owned Drive folder, skips existing matching
  targets on rerun, and writes a JSON report.
- `system1 standardize-archives` extracts zip archives and flattens media
  files, including `.wav`, and JSON files into the System 1 `raw_videos/` and
  `metadata/` input layout. Existing matching flattened files are skipped on
  rerun.
- Drive shadow and archive standardization fail non-zero on item-level errors
  by default; `--allow-partial` is an explicit operator override.
- Notebook 00 runs Drive shadow, archive standardization, standardized input
  readiness checks, local phase00 ingest, batch assignment, then required
  `sync-phase00-ingestion` to the configured Hugging Face Dataset repo under
  `phase00_ingestion/`.
- `system1 sync-phase00-ingestion` and `system1 restore-phase00-ingestion`
  support worker notebooks loading phase output from the same Hugging Face
  Dataset repo.
- `uv run pytest` passed with 103 tests after this phase00 workflow update.

Full MVP-0.6 remains planned until the complete seed path through structure,
features, SQLite/FTS/vector map, validation report, and smoke proof is closed.
