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
  -> bounded temporal probes for novel visual/text events
  -> deterministic representative-keyframe selection
  -> default pinned NeMo/Parakeet Vietnamese ASR, or Faster-Whisper Large-v3 override
  -> OpenCV text-presence gate, then Vintern OCR for uncertain/text frames
  -> shared 4-bit Qwen strict shot-caption JSON, batched over representative frames
  -> ASR-to-shot alignment
  -> shared Qwen multimodal context-focus scene grouping
  -> shared Qwen strict bilingual scene-summary JSON
  -> scoped Gemini fallback for failed semantic requests/runtime
  -> validated per-video structure ZIP
```

Business logic, prompts, schemas, caching, retries, rate limiting, validation,
and artifact writing live in package/CLI code. Notebook 01 remains a thin
operator-facing orchestration surface.

## Runtime Qualification And Worker Smoke Gate

Dependency changes and normal worker execution have separate gates.

The one-time dependency gate starts from a fresh Python 3.13 Colab runtime and
installs base System1 only. `system1-phase01-qualify` composes the union of
`project.dependencies` and `phase01-production`, preserves requirement extras
and markers, applies the named candidate specifiers, installs the full direct
contract in one subprocess, and runs checks in another fresh subprocess. The
result is `phase01_runtime_qualification_v1.json`, including exact installed
versions, ABI/Parquet checks, CUDA, owner-classified `pip check`, real NeMo
restore/transcription, and real Vintern-1B, Vintern-3B, and Qwen inference.
Production NumPy/NeMo/Transformers constraints may change only after that
artifact passes. A fallback candidate must run in a different runtime identity.

Normal workers use `process-batch` directly and never repeat the real smoke as
part of their assigned batch. The optional `phase01-smoke` developer command is
run manually once when full-pipeline implementation evidence is needed.
Runtime-only preflight runs before fixture restore. The package then downloads
pinned `L30_V040` Phase00/raw evidence from Hugging Face, creates a one-row
handoff, and calls the unchanged `process_production_batch()` core. Smoke
release and checkpoint writes go only to configured test repositories under
`_smoke/<run_id>`. A smoke pass requires all of these decision-point sources to
be `computed`:

```text
shots, keyframes, asr, ocr, shot_captions,
shot_transcript_links, scenes, scene_summaries, package, sync
```

The smoke report records dependency/runtime identity, providers, timings,
RAM/VRAM peaks, row counts, representative ASR/OCR/caption/summary rows, package
validation, and remote checksum proof. Local fixture, output, checkpoint cache,
and run scratch are removable while the shared model cache remains. Optional
remote cleanup enumerates and validates each exact object and refuses deletion
unless the repository and `_smoke/<run_id>` prefix match configured test
authority. Smoke success or failure never starts or blocks an assigned
production batch; production scheduling is a separate operator action.

## Notebook And Config Contract

Notebook 01 contains one minimal `USER SETTINGS` cell. It exposes `batch_id`,
`worker_id`, an optional Phase00 `release_id` override, optional
storage/repository overrides, and secret-store lookups. If no release override
is set, package code resolves the Phase00 release. Secrets come from the
environment, Colab Secrets, or Kaggle Secrets and are neither displayed nor
persisted.

The notebook also contains a Markdown-only `OPTIONAL ONE-VIDEO FULL-PIPELINE
SMOKE` block. A developer may copy that thin `phase01-smoke` invocation into a
new code cell after environment/package setup. Markdown is not executed by Run
All, so ordinary workers pay no smoke cost.

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
`scripts/prepare_transnetv2_artifact.py`. The preferred canonical preparation
job checks out the pinned official upstream commit, runs the official
TensorFlow-to-PyTorch converter and its parity tests, then emits the
source/weight checksums. Workers download and validate that immutable bundle;
they never convert weights.

When upstream `soCzech/TransNetV2` is blocked by GitHub LFS quota, the
preparation script also supports an explicit mirror-based unblock path. That
path still copies the PyTorch source from the pinned official commit and
verifies the source SHA-256, but downloads preconverted PyTorch weights from a
declared Hugging Face mirror and verifies the expected weights SHA-256. Mirror
artifacts must declare `artifact_origin=preconverted_huggingface_mirror` and
`conversion_verified=false`; runtime accepts them only when
`configs/models.yaml` intentionally sets `conversion_verified: false`.
Production readiness intentionally fails while the generated weight checksum is
absent from `configs/models.yaml`.

The default artifact location is the configured model-artifact store:
`1thesudden/AIC26_checkpoints` under
`model_artifacts/transnetv2/85cef72af9a916bdfd7cc94a670c9cdfbf12d1ed/`.
Public and private checkpoint datasets are both supported; the preparation
script enforces private storage only when run with `--require-private`.

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
is broken by proximity to the temporal center of the shot. Every mandatory
anchor retains its semantic `early`, `middle`, or `late` role; exactly one
anchor row per shot has `is_representative = true`.

Canonical `keyframes.parquet` additionally records:

```text
keyframe_role
quality_score
is_representative
selection_reason
```

Detailed candidate metrics remain checkpoint/debug evidence instead of
expanding the canonical table.

### Semantic-event supplemental keyframes

The mandatory anchor candidate generation above remains frame-ratio based and
unchanged. For long shots, a second deterministic policy creates temporal probe
IDs from the authoritative Phase00 `frame_timeline.pts_time`. It seeds coverage
with the safe interior start/end plus nominal early/middle/late target
timestamps, then bisects the largest timestamp gap until the configured target
gap is reached or the per-shot probe cap is exhausted. The target gap is best
effort; diagnostics record `coverage_cap_reached` and the remaining maximum gap
when the cap prevents full coverage. If the initial seed-to-seed gaps are
already within the target, the shot exposes no semantic candidates; this keeps
short shots on the mandatory anchor path only.

Probe IDs are temporary observations, not automatically persisted keyframes.
For shots requiring semantic sampling, anchor candidate IDs, coverage-seed IDs,
and bisection probe IDs are combined before one grouped decode pass. After
actual anchors are selected, every valid coverage seed or probe that is not
already an actual anchor is compared with all retained references using
normalized dHash visual distance and Jaccard distance between config-sized,
MSER-masked Canny edge signatures for text-region change.

Visual novelty is the minimum distance to every retained reference, so a probe
must differ from all already retained visual evidence. Text change can trigger
only when the candidate itself has plausible text; text disappearing does not
count as new evidence. A candidate is eligible when either signal crosses its
configured threshold. Selection is greedy and recomputes novelty after each
accepted frame. Ranking is deterministic: triggered-signal count, strongest
triggered-signal score, quality, timestamp distance to the nearest actual
anchor, then lower `frame_id`. Configured timestamp separation and a maximum of
two supplemental frames per shot bound output size.

Accepted rows use `keyframe_role = supplemental`, are never representative, and
are covered by `keyframes_v3`. OCR runs on them through the existing text gate;
their OCR joins the shot's scene evidence, and focused scene review can include
all supplemental images without role-key overwrite. Shot captioning and scene
summary image sampling remain representative-only.

`keyframe_diagnostics.jsonl` records candidate source, timestamp gap, quality,
visual/text scores, triggered-signal count, keep/drop reason, temporal distance,
dedup target, signal errors, and coverage-cap state. These diagnostics do not
expand the canonical Parquet schema.

Candidate decoding remains one forward pass through the video, grouped by
shot. Only one shot's temporary anchor/probe frames remain in memory at a time;
selected images are written before the group is released. This preserves the
coverage policy without retaining all frames for a long video.

## ASR

Production ASR configuration:

```text
default provider = nemo
default model = nvidia/parakeet-ctc-0.6b-vi
default revision = b0493142b49458810324e3db8be9e8e07b4ebc17
default model file = parakeet-ctc-0.6b-vi.nemo
segmentation = FFmpeg silence detection with bounded max segment length
optional provider = faster_whisper
optional model = Systran/faster-whisper-large-v3 at its configured revision
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

## OCR And Canonical Shot Captions

Each representative keyframe first passes a conservative OpenCV text-presence
gate. Only a high-confidence no-text decision skips Vintern. Uncertain results
and gate errors run the pinned Vintern OCR model. A skipped image still emits a
canonical `ocr_v2` row with empty text, `status=empty`, and gate provenance;
gate counts and failures stay in diagnostics. Thresholds are versioned in
`phase01.yaml` and participate in the OCR stage fingerprint.

Each shot has exactly one caption row generated from its selected
representative keyframe. Qwen2.5-VL-7B-Instruct is primary and generates each
caption field as plain text using the prompt-version mapping in `models.yaml`.
The caption rows use the canonical `shot_captions_v4` contract.

```json
{
  "caption_vi": "...",
  "caption_en": "...",
  "objects_vi": ["..."],
  "objects_en": ["..."],
  "actions_vi": ["..."],
  "actions_en": ["..."],
  "visible_text_summary_vi": "...",
  "visible_text_summary_en": "..."
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
objects_vi
objects_en
actions_vi
actions_en
visible_text_summary_vi
visible_text_summary_en

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

Caption requests require per-request content-addressed caching, bounded retry,
resumability, exact model/version, prompt version, response-schema version, and
non-secret diagnostics. Local requests use true processor/model tensor
batching, not thread concurrency. Invalid JSON/schema for one request falls
back only that request to Gemini; systemic local-runtime failure opens the
chunk circuit and sends the remaining semantic work to Gemini.

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

Its inputs are ordered shots, representative images, optional
early/late/supplemental images for focused review, bilingual shot captions,
caption objects/actions, canonical OCR, ASR transcript evidence, and the
timeline. It does not use organizer support artifacts, embeddings, or organizer
metadata as boundary evidence.

The configured structured client returns only strict Boolean adjacent-shot
boundary judgements. Qwen is primary and Gemini is fallback. Package
code owns overlap voting, ambiguity review, consistency review, deterministic
scene partitioning, IDs, ranges, mappings, and validation. Every shot belongs
to exactly one scene; scenes cannot overlap, leave a shot-order gap, or reorder
shots.

A valid all-false boundary result creates one successful scene. Failure of both
the local primary and configured fallback after bounded retry fails the video;
production does not turn an unresolved result into one fabricated scene.

## Bilingual Scene Summaries

Only after scene boundaries are fixed, the same shared Qwen runtime receives
the scene's sampled representative images, bilingual shot captions,
objects/actions, OCR, ASR transcript evidence, and timeline. Gemini receives
the same request only when fallback is required. Both return strict JSON:

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
|-- ocr.parquet
|-- shot_captions.parquet
|-- asr_segments.parquet
|-- shot_transcript_links.parquet
|-- scenes.parquet
|-- scene_transcript_links.parquet
|-- scene_summaries.parquet
|-- keyframes/
|-- thumbnails/
|-- diagnostics/
|   |-- keyframe_diagnostics.jsonl
|   |-- scene_boundary_diagnostics.jsonl
|   |-- transnet_predictions.json
|   |-- asr_status.json
|   `-- ocr_status.json
|-- manifest.json
|-- artifact_manifest.json
|-- checksums.json
|-- resolved_config.json
`-- errors.jsonl
```

`scene_transcript_links.parquet` is retained even though it was omitted from
the proposed list. It is the canonical direct mapping from scene context to ASR
segments used by System 2 and is already part of the repository data contract.
It is derived after the scene partition is fixed.

Contact sheets, raw provider responses, retry logs, and request caches are
intermediate/checkpoint data and are not canonical runtime tables.

## Notebook 02 Handoff

Notebook 02 consumes keyframes and evidence generated by Notebook 01 and
creates:

```text
configured object detection
SigLIP embeddings
BEiT3 embeddings
```

The exact object detector and exact SigLIP/BEiT3 model identifiers are
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
- Stage completion is atomic: write local temp, validate, checksum, then upload
  the immutable outputs and matching complete `state.json` in one backend
  commit. Local Colab/Kaggle storage is scratch, not resume authority.
- A rerun reuses only complete stages whose persistent outputs, checksums,
  upstream fingerprints, and relevant versions still match. Dependency changes
  invalidate only downstream stages.
- Worker reports and `errors.jsonl` distinguish failed, no-audio/no-speech, and
  successful-empty states.

Notebook 01 processes a resource-aware chunk of videos while preserving one
heavy local VLM resident at a time. Vintern serves OCR and is released before
Qwen loads. One Qwen processor/model session is then reused for shot captions,
scene boundaries, and scene summaries across the chunk before release. Package
code drops model/tensor references, runs garbage collection, and clears unused
CUDA cache at lifecycle boundaries. Model files may remain in the runtime's
Hugging Face cache, separate from persistent stage checkpoints.

Raw-media downloads, Phase00 restore, checkpoint restore/verification,
model-artifact downloads, and release checksum verification use bounded caches
inside run/video scratch. Those caches are removed after the relevant restore
or after each video. Structured progress records expose batch/video/stage
status and remaining scratch space without printing credentials.

Qwen is loaded explicitly with bitsandbytes NF4 4-bit, float16 compute, and
double quantization on CUDA; load failure never silently retries the same
checkpoint in full precision or with CPU/disk offload. Caption batches default
to two and reduce on CUDA OOM until one. OCR batches default to four, but
Vintern uses batches only when its model exposes a safe native API. Scene
boundary and summary requests stay at one because they carry multi-image
context. Repeated batch-one OOM or an unusable local runtime opens a per-chunk
circuit breaker; isolated JSON/schema errors fall back per request without
disabling Qwen. Gemini concurrency is unchanged.

Structured request-level content-addressed cache entries live in the current
video's stage scratch. The completed canonical stage is the persistent cache
and is promoted to the configured writable checkpoint repository, which may be
public or private. This avoids one Hugging Face commit per Gemini request while
preserving stage-level resume semantics.
All output files belonging to one checkpoint stage and the matching
`state.json` completion marker are uploaded in one atomic backend commit. A
resume still downloads and verifies every recorded checksum; a missing or
corrupt output invalidates that stage and its downstream stages.

After the worker report commit, Notebook 01 lists the remote
`{release_id}/phase01_structure` tree and fails unless every completed video
package plus the report, error log, and manual-review report is present.

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
