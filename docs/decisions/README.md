# Decisions

Decision records preserve lasting product, architecture, data ownership,
security, compatibility, and validation choices that future work must inherit.

Use `docs/templates/decision.md`. Task-local implementation choices remain in
the active execution plan and do not require a separate decision.

An installed consumer begins with no fabricated decisions. Add local decision
documents here as real choices are accepted, then index them in this file.

## Recent Accepted Decisions

- `0026-deterministic-scene-grouping.md`: scenes return as a deterministic,
  model-free grouping of consecutive shots from SigLIP, caption, ASR, and OCR
  evidence, with a text-only scene summary. Amends 0021 decision 3.
- `0025-caption-pass-and-release-storage.md`: captions run in a separate pass
  over worker packages; the runtime release is published to a Hugging Face
  Storage Bucket with WebP keyframes re-encoded at release time. Amends 0023
  and the target doc layout.
- `0024-pipeline-validation-policy.md`: fail fast on corrupted data, degrade and
  record on missing evidence, check output content instead of environment
  exactness, and test behavior instead of configuration constants.
- `0023-phase01-model-stack-revision.md`: real image embeddings, hybrid text
  retrieval (FTS5 plus multilingual text embeddings),
  ASR and OCR replacement, and one constrained Vietnamese caption
  call per shot. Models fixed after Kaggle trials: SigLIP2, multilingual-e5-large,
  ChunkFormer, EasyOCR + VietOCR, Qwen3-VL-4B. Supersedes 0018 and 0020.
- `0022-content-adaptive-keyframe-sampling.md`: keyframe density follows
  visual change with sub-shots for long shots. Amends 0019.
- `0021-shot-level-retrieval-units.md` (decision 3 amended by 0026): no VLM
  scene grouping or VLM scene summaries; multi-shot context is computed at
  query time. Supersedes 0014.

Earlier decisions (superseded or amended ones are marked):

- `0020-phase01-speech-aware-asr-decoding.md` (superseded by 0023): Phase01 uses bounded Silero VAD,
  a 30-second hard cap, pinned 4-gram Flashlight beam decoding, and auditable
  acoustic/lexical gates without greedy fallback.
- `0019-phase01-semantic-event-keyframes.md` (amended by 0022): Phase01 preserves mandatory
  early/middle/late anchors and adds bounded timestamp probes that persist only
  visually novel or text-changing non-representative supplemental keyframes.
- `0018-phase01-local-first-semantic-runtime.md` (superseded by 0023): Notebook 01 defaults to
  NVIDIA Vietnamese FastConformer ASR, gated Vintern OCR, and one shared
  4-bit Qwen2.5-VL runtime for all semantic stages, with an exclusive sticky
  Vintern-3B-R local fallback.
- `0017-raw-upload-decoded-frame-timelines.md`: Notebook 00B/00C build required
  decoded timelines while each video is already in bounded raw-upload scratch;
  canonical HF ingest validates the compact Parquet without re-downloading the
  MP4.
- `0016-canonical-per-video-metadata.md`: organizer metadata remains optional,
  but Notebook 00B/00C create one schema-valid canonical metadata JSON per
  video from organizer fields plus `ffprobe` facts while preserving provenance
  and the pre-generation missing-metadata audit.
- `0014-multimodal-context-window-scene-grouping.md` (superseded by 0021): Phase01 scene boundaries
  are judged in overlapping multimodal context/focus windows while deterministic
  package code owns the final partition, IDs, ranges, validation, and explicit
  failure behavior.
- `0015-system1-self-generated-production-evidence.md` (amended by 0021 and 0023): System 1 consumes videos
  plus optional metadata, regenerates derived evidence, fixes the Notebook 01
  production pipeline, and builds separate SigLIP/BEiT3 indexes in Notebook 02.
