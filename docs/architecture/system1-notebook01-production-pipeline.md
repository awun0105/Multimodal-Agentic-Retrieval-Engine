# System 1 Notebook 01 Production Pipeline

Date: 2026-08-05

## Status

Accepted and implemented package contract for production `phase01_structure`.
Automated tests cover deterministic stage/checkpoint/package behavior; a
real-provider acceptance run remains required before operational readiness may
be claimed.

Test doubles and timeline-aware fixtures remain injectable only through guarded
test hooks. Notebook 01 and the public Phase01 CLI expose one production
pipeline and no execution/provider selector. A production run never silently
replaces a failed stage with fabricated semantic output.

## Source Policy

Notebook 01 consumes only:

```text
official organizer video
optional organizer metadata paired by video_id
Phase00 facts derived from that video
```

Phase00 facts include the canonical video inventory, media mapping, probe
facts, decoded frame timeline, and batch manifests. They are project-generated
facts, not organizer-derived retrieval artifacts.

The project does not ingest or index organizer-provided keyframes, object JSON,
CLIP features, map-keyframes, or media-info. Those files remain documented as
officially available support material, but System 1 intentionally regenerates
all derived retrieval data to keep one frame-ID, provenance, model, and quality
contract.

## Production Sequence

```text
official video
  -> TransNet V2 shot detection
  -> early/middle/late keyframes from bands centered at 20%/50%/80%
  -> deterministic representative-keyframe selection
  -> faster-whisper large-v3 ASR with automatic language and VAD
  -> Gemini strict bilingual caption JSON, one response per shot
  -> ASR-to-shot alignment
  -> multimodal context-focus scene grouping
  -> Gemini strict bilingual scene-summary JSON
  -> validated per-video structure ZIP
```

Business logic, prompts, schemas, caching, retries, rate limiting, validation,
and artifact writing live in package/CLI code. Notebook 01 remains a thin
operator-facing orchestration surface.

## Notebook And Config Contract

Notebook 01 contains one minimal `USER SETTINGS` cell. It exposes `batch_id`,
`worker_id`, an optional Phase00 `release_id` override, optional
storage/repository overrides, and secret-store lookups. If no release override
is set, package code resolves the Phase00 release. Secrets come from the
environment, Colab Secrets, or Kaggle Secrets and are neither displayed nor
persisted.

Auto-resolution selects the unique completed Phase00 release with the latest
`completed_at`. Missing timestamps or a latest-time tie fail explicitly. A
legacy release created before `completed_at` was added remains usable only with
`release_id_override`; for the currently published legacy v001 snapshot, set
that override to `canonical_release_v001`.

Phase00 restore is batch-scoped: download the two canonical tables, the
selected batch manifest, and only the decoded frame timelines referenced by
that batch. A checksum marker makes the restore resumable and detects local
corruption. Notebook 01 does not download every Phase00 timeline merely to
process one batch.

All deterministic settings live in versioned repository YAML: exact model IDs
and revisions, schema and prompt versions, file naming and media encoding,
TransNet, ASR, keyframe selection, scene grouping, retry/concurrency, and
artifact/checkpoint layout. Notebook cells do not duplicate these values.

At startup package code merges:

```text
repository YAML
+ USER SETTINGS
+ detected runtime environment
+ resolved Phase00 release
  -> ResolvedConfig
```

It persists a secret-free `resolved_config.json` and full SHA-256
`config_hash`. Production preflight fails before expensive processing if any
required deterministic value is unresolved.

## Shot Detection

Production uses TransNet V2 only.

Runtime consumes a project-owned PyTorch artifact created once by
`scripts/prepare_transnetv2_artifact.py`. The preparation job checks out the
pinned official upstream commit, runs the official TensorFlow-to-PyTorch
converter and its parity tests, then emits the source/weight checksums. Workers
download and validate that immutable bundle; they never convert weights.
Production readiness intentionally fails while the generated weight checksum
is absent from `configs/models.yaml`.

- A successful inference with no detected transition is valid: emit one shot
  covering the complete decoded video with a successful
  `transnet_v2_no_cut` method/status.
- A model load, decode, dependency, or inference error after bounded retry
  fails that video. Do not silently emit `fallback_full_video` in production.
- Test/mock profiles may keep explicit fallback fixtures, but their manifests
  must identify them as non-production.
- Shot ranges use `[start_frame, end_frame)` and decoded original frame IDs.
- Shot IDs remain `{video_id}_SH{shot_index:05d}`, zero-based in timeline order.

## Search-Band Keyframes

The nominal `20%`, `50%`, and `80%` positions are semantic centers of three
search bands, not exact frames that must be selected:

```text
early:  search 10%-30%, target 20%
middle: search 40%-60%, target 50%
late:   search 70%-90%, target 80%
```

Each band samples at most five candidate decoded-frame IDs, distributed evenly
by the decoded Phase00 timeline. Candidates are temporary selection inputs and
are not all persisted as canonical keyframes. Candidate validation checks that
the frame decodes and is not abnormally near-black or near-white according to
versioned config. Sharpness is measured as variance of Laplacian after every
candidate is resized to the same configured resolution.

There is no absolute dataset-wide blur threshold. Within one band, package code
filters invalid candidates, chooses the highest sharpness score, and breaks a
tie by choosing the frame closest to that band's target. If a band has no valid
candidate, it expands the search toward the nearest safe interior of the shot
while avoiding the shot boundaries. If the shot contains no decodable valid
frame, keyframe extraction and therefore the video fail.

Selected frame IDs are deduplicated. A short shot may therefore persist only
one or two canonical keyframes; it never duplicates a `keyframe_id` merely to
satisfy three roles. If only one frame remains, that frame is representative.

Canonical identity remains:

```text
frame_id    = decoded original frame index
keyframe_id = {video_id}:{frame_id}
```

For multiple selected roles, let `best_quality` be the maximum comparable
Laplacian-variance quality score. Middle is representative when:

```text
middle_quality >= 0.85 * best_quality
```

Otherwise the highest-quality selected role is representative. A quality tie
is broken by proximity to the temporal center of the shot. Every persisted row
retains its semantic `early`, `middle`, or `late` role; exactly one row per shot
has `is_representative = true`.

Canonical `keyframes.parquet` additionally records:

```text
keyframe_role
quality_score
is_representative
selection_reason
```

Detailed candidate metrics remain checkpoint/debug evidence instead of
expanding the canonical table.

Candidate decoding is a single forward pass through the video, grouped by shot.
Only one shot's temporary candidate frames remain in memory at a time; selected
images are written before the group is released. This preserves the search
policy without retaining all full-resolution candidates for a long video.

## ASR

Production ASR configuration:

```text
provider = faster-whisper
model = large-v3
language = auto
VAD = enabled
```

ASR runs for every video.

- No audio stream: record video ASR status `no_audio`; emit an empty,
  schema-valid `asr_segments.parquet` and empty
  `shot_transcript_links.parquet`; continue the video.
- Audio exists but contains no speech after successful inference: record
  `no_speech`; emit empty schema-valid ASR/link tables; continue.
- Audio exists but extraction/model/inference fails after bounded retry: fail
  the video.
- Every non-empty ASR row stores `asr_segment_id`, `video_id`, time range,
  decoded-frame range when resolvable, text, detected language, confidence when
  available, provider/model/version, and status.

## Canonical Shot Captions

Each shot has exactly one caption row generated from its selected
representative keyframe. Gemini must return strict JSON:

```json
{
  "caption_vi": "...",
  "caption_en": "..."
}
```

Both fields are non-empty strings in a successful production row. The provider
adapter validates the response schema and rejects extra/missing/wrongly typed
fields according to the versioned contract.

Canonical `shot_captions.parquet` is one row per shot:

```text
shot_caption_id
video_id
shot_id
representative_keyframe_id
representative_timestamp_sec
caption_vi
caption_en
provider
model_name
model_version
prompt_version
schema_version
confidence
status
```

There is no canonical per-keyframe `image_captions` table. The API's raw JSON
belongs in the content-addressed cache/diagnostics; the normalized bilingual
fields belong in Parquet.

Caption requests require content-addressed caching, bounded retry, rate-limit
handling, resumability, exact model/version, prompt version, response-schema
version, and non-secret diagnostics. A persistent caption failure fails the
video because canonical captions are required for scene grouping.

## Transcript-Shot Alignment

`shot_transcript_links.parquet` links ASR segments to every overlapping shot.
It contains at least:

```text
video_id
shot_id
asr_segment_id
coverage
```

Coverage is derived deterministically from time overlap. Empty `no_audio` or
`no_speech` ASR produces an empty schema-valid link table, not fabricated text.

## Scene Grouping

The authoritative algorithm is
`docs/architecture/system1-scene-grouping.md`.

Its inputs are ordered shots, representative images, optional early/late images
for focused review, bilingual shot captions, ASR transcript evidence, and the
timeline. It does not use organizer support artifacts, OCR, objects,
embeddings, or metadata as boundary evidence.

Gemini returns only strict Boolean adjacent-shot boundary judgements. Package
code owns overlap voting, ambiguity review, consistency review, deterministic
scene partitioning, IDs, ranges, mappings, and validation. Every shot belongs
to exactly one scene; scenes cannot overlap, leave a shot-order gap, or reorder
shots.

A valid all-false boundary result creates one successful scene. Gemini/provider
failure after bounded retry fails the video; production does not silently turn
an unresolved result into one fallback scene.

## Bilingual Scene Summaries

Only after scene boundaries are fixed, Gemini receives the scene's ordered
representative images, bilingual shot captions, ASR transcript evidence, and
timeline. It returns strict JSON:

```json
{
  "summary_vi": "...",
  "summary_en": "..."
}
```

Canonical `scene_summaries.parquet` is one row per scene:

```text
scene_id
video_id
summary_vi
summary_en
provider
model_name
model_version
prompt_version
schema_version
confidence
status
```

Summary calls use the same cache/retry/rate-limit/resume/provenance rules as
caption calls. Persistent summary failure fails the video. Earlier
`scene_summary_initial` / `scene_summary_enriched` fields are retired; one
canonical bilingual summary row is produced after the final scene partition.

## Structure Artifact Contract

The per-video structure package is:

```text
{video_id}/
|-- metadata_normalized.json
|-- shots.parquet
|-- keyframes.parquet
|-- shot_captions.parquet
|-- asr_segments.parquet
|-- shot_transcript_links.parquet
|-- scenes.parquet
|-- scene_transcript_links.parquet
|-- scene_summaries.parquet
|-- keyframes/
|-- thumbnails/
|-- manifest.json
|-- artifact_manifest.json
|-- checksums.json
`-- errors.jsonl
```

`scene_transcript_links.parquet` is retained even though it was omitted from
the proposed list. It is the canonical direct mapping from scene context to ASR
segments used by System 2 and is already part of the repository data contract.
It is derived after the scene partition is fixed.

Contact sheets, raw Gemini responses, retry logs, and API caches are
intermediate/checkpoint data and are not canonical runtime tables.

## Notebook 02 Handoff

Notebook 02 consumes only keyframes generated by Notebook 01 and creates:

```text
Gemini OCR
configured object detection
SigLIP embeddings
BEiT3 embeddings
```

The exact object detector and exact Gemini/SigLIP/BEiT3 model identifiers are
configuration values that must be recorded in manifests; no unspecified model
may be presented as reproducible production behavior.

SigLIP and BEiT3 use separate index names and separate FAISS files. They share
the canonical `embeddings_meta` and `vector_map` schemas:

```text
embeddings_meta: multiple rows per keyframe, distinguished by index_name/model
vector_map: unique key = (index_name, vector_id)
```

Recommended physical layout:

```text
feature artifact:
  embeddings/siglip.npy
  embeddings/beit3.npy
  embeddings_meta.parquet

runtime release:
  indexes/siglip.faiss
  indexes/beit3.faiss
  indexes/vector_map.parquet
```

This avoids separate duplicate metadata schemas while preserving two genuinely
independent retrieval indexes.

## Production Failure And Resume Rules

- Notebook 01 and public Phase01 commands have no production profile/provider
  selector. Test doubles are test-only dependency injection.
- A successful no-cut TransNet result, `no_audio`, or `no_speech` is a valid
  observed state, not a fallback.
- Model/decode/inference/API failure after bounded retry fails the video at the
  responsible stage.
- The checkpoint key is `release_id + video_id + stage`. Stages are `shots`,
  `keyframes`, `asr`, `shot_captions`, `shot_transcript_links`, `scenes`,
  `scene_summaries`, `package`, and `sync`.
- Each stage stores status, input fingerprint, relevant config hash,
  model/revision, prompt version when applicable, schema version, output
  checksums, and completion time.
- Stage completion is atomic: write local temp, validate, checksum, sync to the
  persistent artifact store, update `state.json`, then mark complete. Local
  Colab/Kaggle storage is scratch, not resume authority.
- A rerun reuses only complete stages whose persistent outputs, checksums,
  upstream fingerprints, and relevant versions still match. Dependency changes
  invalidate only downstream stages.
- Worker reports and `errors.jsonl` distinguish failed, no-audio/no-speech, and
  successful-empty states.

Notebook 01 processes one video at a time. TransNet and faster-whisper do not
remain resident together; after each GPU-heavy stage package code drops model
and tensor references, runs garbage collection, and clears unused CUDA cache.
Model weights may remain in the runtime's Hugging Face cache, which is separate
from persistent stage checkpoints.

Faster-whisper uses CUDA `float16`, retries an OOM with CUDA `int8_float16`, and
uses CPU `int8`; it does not replace large-v3 with a weaker model. If bounded
OOM recovery is exhausted, the video becomes `failed_retryable`, its error is
checkpointed, scratch/GPU state is cleaned, and processing continues with the
next video. Gemini calls use bounded concurrency, initially two requests within
the current video.

Gemini request-level content-addressed cache entries live in the current
video's stage scratch. The completed canonical stage is the persistent cache
and is promoted to the private checkpoint repository. This avoids one Hugging
Face commit per Gemini request while preserving stage-level resume semantics.
All output files belonging to one checkpoint stage are uploaded in one backend
commit; the separate `state.json` update remains the final atomic completion
marker after output checksum verification.

## Validation Sequence

Production implementation is proven in this order:

1. One real video exercises all applicable stages and artifact validation.
2. A small heterogeneous batch proves resume, failure isolation, cache reuse,
   batching, ZIP sync/restore, and model/API limits.
3. Full Batch 1 runs only after the small batch passes.

Mock tests remain useful for deterministic package contracts, but they do not
prove production provider quality or preliminary readiness.

## Implementation Map

- `src/system1/phase01/runner.py`: release discovery/restore, config, preflight,
  model artifact materialization, and batch entry point.
- `src/system1/phase01/checkpoint.py`: per-video stage state, checksum restore,
  stage fingerprints, and dependency invalidation.
- `src/system1/phase01/production.py`: sequential orchestration, packaging,
  sync verification, failure isolation, and reporting.
- `src/system1/shots/`, `keyframes/`, `asr/`, `gemini/`, and `scenes/`: fixed
  production stage implementations.
- `src/system1/phase01/validation.py` and `qa.py`: strict canonical package gate
  and deterministic manual-review sampling.
- `notebooks/01_worker_structure_pipeline.ipynb`: minimal operator settings and
  one package CLI invocation.
