# MVP-0.6 System 1 Mini Seed Dataset And Validation

## Status

planned

## Lane

normal

## Product Contract

Create the smallest executable System 1 slice that proves the app-ready data
contract can be built from real organizer-style inputs: paired raw `.mp4`
videos and per-video metadata JSON matched by filename stem.

This story does not build the full competition pipeline. It creates a tiny
seed path that proves the repo can discover inputs, assign stable IDs, generate
minimal derived media, build app-ready SQLite/FTS/vector mapping fixtures, and
emit a validation report that System 2 can trust.

## Relevant Product Docs

- `docs/architecture/system1-ingestion.md`
- `docs/architecture/data-contracts.md`
- `docs/planning/implementation-phases/phase-01-system1-mini-seed-and-validation.md`
- `docs/validation/test-matrix.md`
- `system1_spec.md`

## Implementation Tickets

### Ticket 1 — Tiny Seed Dataset Layout

Goal: define a tiny seed input layout using 1-2 paired raw videos and metadata JSON files.

Scope:

- Choose or document the fixture location.
- Keep raw media out of the repo unless intentionally tiny.
- Record expected folder names for raw videos and metadata JSON.

Acceptance criteria:

- Raw video and metadata roots are configurable.
- Each fixture pair uses the same filename stem.
- Missing, duplicate, or extra stems are treated as validation errors.

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
- Prefer decoded frame count when available.
- Emit `frame_count`, `frame_count_estimated`, `frame_count_method`, `fps_detected`, `fps_source`, `is_vfr`, and `frame_id_method`.
- Emit `frame_timeline` staging rows or documented equivalent proof when frame-accurate timestamp mapping is needed.

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
- If shot detection is unavailable for the seed path, a fallback full-video shot is emitted with degraded status.
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

- A tiny paired seed dataset path exists or is documented as an operator-provided input.
- System 1 mini can build app-ready seed artifacts from raw video + metadata JSON roots.
- Generated `app.sqlite` contains canonical IDs, logical refs, minimal FTS5/text evidence, `vector_map`, and `feature_availability`.
- Validation report proves pairing, refs, frame metadata, vector map, and SQLite path safety.
- The story leaves full dataset ingestion, advanced OCR/ASR/caption quality, and full FAISS scale to later stories.

## Design Notes

- Commands: prefer a small CLI such as `aic-prepare build --dataset-id ... --raw-video-dir ... --metadata-dir ... --data-root ... --runtime-root ... --report ...` when implementation begins.
- Queries: System 2 should be able to resolve `video_id/frame_id`, `keyframe_id`, and `vector_id -> keyframe_id` from `app.sqlite`.
- API: no runtime API is required in this story.
- Tables: seed path should cover `videos`, `shots`, `keyframes`, `vector_map`, `feature_availability`, and minimal FTS/text evidence tables.
- Domain rules: `video_id` is filename stem; `video_ref` is canonical raw-video logical ref; `keyframe_ref`/`thumbnail_ref` are canonical derived media refs; no absolute paths in runtime SQLite.
- UI surfaces: not applicable; System 2 UI starts after app-ready seed artifacts exist.

## Validation

When updating durable proof status, use numeric booleans:
`scripts/bin/harness-cli story update --id MVP-0.6 --unit 1 --integration 1 --e2e 0 --platform 0`.

| Layer | Expected proof |
| --- | --- |
| Unit | Pairing, ID, path/ref, frame metadata, and validation helper tests. |
| Integration | Build seed artifacts from tiny paired inputs and inspect `app.sqlite` plus validation report. |
| E2E | Not expected for this story. |
| Platform | Optional operator smoke command proving local build works with configured roots. |
| Release | Validation report and matrix update when implemented. |

## Harness Delta

No Harness changes required for story creation. When implemented, update
`docs/validation/test-matrix.md` and durable story status with real proof.

## Evidence

No implementation evidence yet. Add commands, reports, and artifact paths after
the System 1 mini build exists.
