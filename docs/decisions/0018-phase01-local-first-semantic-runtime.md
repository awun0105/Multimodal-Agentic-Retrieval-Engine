# ADR 0018: Phase01 Local-First Semantic Runtime

Date: 2026-08-25

## Status

Accepted

## Context

Notebook 01 must run on a laptop GPU and free Colab/Kaggle runtimes without
making a paid API the normal path. Phase01 already schedules bounded video
chunks, checkpoints every canonical stage, and permits only one heavy local
vision model to be resident at a time. Its semantic stages nevertheless used
different provider lifecycles: local Qwen captioned shots while Gemini judged
scene boundaries and summarized scenes.

OCR also ran Vintern on every representative frame, including obvious no-text
images. Local Qwen accepted only one request at a time and was loaded for the
caption stage rather than being shared across all semantic stages.

## Decision

Phase01 uses this production graph by default:

```text
NVIDIA Parakeet FastConformer CTC 0.6B Vietnamese -> ASR
OpenCV conservative text gate -> Vintern-1B-v3_5 -> OCR
Qwen2.5-VL-7B-Instruct, bitsandbytes NF4 4-bit
  -> shot captions -> scene-boundary judgements -> scene summaries
Gemini -> request-level or chunk-level semantic fallback
```

The Qwen processor and weights are loaded once per runtime chunk and reused by
the three semantic stages. Vintern is released before Qwen loads, preserving
the one-heavy-local-VLM invariant. Shot captions use true tensor batching with
a configured default of two. OCR requests use a configured default of four,
but Vintern batches only when its remote-code implementation exposes a safe
native batch API; otherwise its effective batch size is one.

CUDA OOM reduces a local batch geometrically to one. A malformed or
schema-invalid response falls back to Gemini for only that request. A Qwen load
failure, repeated CUDA OOM at batch size one, or unusable CUDA/model runtime
opens a per-chunk circuit breaker and sends the remaining semantic requests to
Gemini. Gemini remains optional when no fallback is needed and its concurrency
is not increased.

The OCR gate may skip Vintern only for high-confidence no-text images. It still
emits a canonical `ocr_v2` row with empty text and `status=empty`; uncertain
images and detector errors continue to Vintern. Gate thresholds live in
versioned Phase01 config and therefore participate in OCR checkpoint identity.

ASR defaults to the pinned `nvidia/parakeet-ctc-0.6b-vi` Hugging Face alias and
NeMo 2.6. Faster-Whisper Large-v3 remains an explicit config override. Provider,
model, prompt, schema, OCR policy, and quantization changes invalidate the
affected stage and its downstream dependants. Execution-only batch sizes do
not alter semantic checkpoint identity.

## Alternatives Considered

1. Keep Gemini primary for scene boundaries and summaries. Rejected because a
   key and quota would remain mandatory for a normal Notebook 01 run.
2. Use ThreadPool-based local inference. Rejected because it does not provide
   true GPU tensor batching and can duplicate model pressure.
3. Run Vintern on every frame. Rejected because obvious no-text frames consume
   GPU time without adding OCR evidence.
4. Switch to Qwen3-VL. Deferred; this phase intentionally retains the existing
   pinned Qwen2.5-VL-7B checkpoint.
5. Let the model return complete scene ranges. Rejected; deterministic package
   code continues to own the contiguous scene partition and validation.

## Consequences

Positive:

- Notebook 01 can complete without Gemini when local providers succeed.
- One Qwen load serves caption, scene grouping, and summary work in a chunk.
- True batching improves shot-caption throughput while adaptive OOM recovery
  protects 16 GB GPU runtimes.
- Request-local fallback avoids abandoning Qwen after isolated output errors.
- OCR compute is reduced without changing the canonical OCR schema.

Tradeoffs:

- NeMo, bitsandbytes, and local VLM dependencies increase environment setup
  size and require real Colab/Kaggle validation.
- Qwen structured output still needs schema validation and Gemini fallback.
- Thresholds and effective batch sizes require telemetry-guided tuning on real
  videos and GPUs.

## Follow-Up

- Run one real video on a T4-class Colab/Kaggle runtime and inspect telemetry,
  OCR gate decisions, captions, scene boundaries, and summaries.
- Run a heterogeneous small batch to prove resume, HF synchronization, disk
  bounds, and circuit-breaker behavior before a full dataset run.
