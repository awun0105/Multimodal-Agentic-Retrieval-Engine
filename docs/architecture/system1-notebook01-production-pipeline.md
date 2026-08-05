# System 1 Notebook 01 Production Pipeline

Date: 2026-08-05

## Status

Accepted target contract for production `phase01_structure`.

The existing package and Notebook 01 orchestration are partial. Mock and
timeline-aware fallback behavior may remain for deterministic tests, but a
production run is not allowed to select mock providers or silently replace a
failed production stage with fabricated semantic output.

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
  -> early/middle/late keyframes near 20%/50%/80% of each shot
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

## Shot Detection

Production uses TransNet V2 only.

- A successful inference with no detected transition is valid: emit one shot
  covering the complete decoded video with a successful
  `transnet_v2_no_cut` method/status.
- A model load, decode, dependency, or inference error after bounded retry
  fails that video. Do not silently emit `fallback_full_video` in production.
- Test/mock profiles may keep explicit fallback fixtures, but their manifests
  must identify them as non-production.
- Shot ranges use `[start_frame, end_frame)` and decoded original frame IDs.
- Shot IDs remain `{video_id}_SH{shot_index:05d}`, zero-based in timeline order.

## Three Keyframes Per Shot

For a shot with `start_frame`, exclusive `end_frame`, and
`frame_count = end_frame - start_frame`, the nominal role targets are:

```text
early  = 20%
middle = 50%
late   = 80%
```

Target positions are mapped to decoded original frame indexes inside the shot,
never to codec I-frames. The implementation uses a deterministic, versioned
rounding/clamping policy and records the actual frame ID and selection method.

For normal shots, the three selected frame IDs must be distinct. A shot with
fewer than three decodable frames cannot physically produce three distinct
canonical `keyframe_id` values. In that edge case, emit every distinct
decodable frame once, record `short_shot_keyframe_count`, and do not duplicate a
`keyframe_id` merely to satisfy a count. If no frame can be decoded, fail the
video.

Canonical identity remains:

```text
frame_id    = decoded original frame index
keyframe_id = {video_id}:{frame_id}
```

The middle keyframe is the first representative candidate. Package code checks
decode success plus versioned blur/black-frame quality rules. If middle fails,
try early and then late. If all available candidates fail quality/decode checks,
the shot cannot receive its required caption and the video fails. The selected
row has `is_representative = true`; the other rows remain retrieval/inspection
keyframes with their `early`, `middle`, or `late` roles.

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

- Production profiles must not select mock providers.
- A successful no-cut TransNet result, `no_audio`, or `no_speech` is a valid
  observed state, not a fallback.
- Model/decode/inference/API failure after bounded retry fails the video at the
  responsible stage.
- Every API/model stage uses deterministic cache keys, resumable checkpoints,
  model/config/prompt/schema provenance, and bounded retries.
- A rerun may reuse only cache/checkpoint entries whose complete inputs and
  versions match.
- Worker reports and `errors.jsonl` distinguish failed, no-audio/no-speech, and
  successful-empty states.

## Validation Sequence

Production implementation is proven in this order:

1. One real video exercises all applicable stages and artifact validation.
2. A small heterogeneous batch proves resume, failure isolation, cache reuse,
   batching, ZIP sync/restore, and model/API limits.
3. Full Batch 1 runs only after the small batch passes.

Mock tests remain useful for deterministic package contracts, but they do not
prove production provider quality or preliminary readiness.
