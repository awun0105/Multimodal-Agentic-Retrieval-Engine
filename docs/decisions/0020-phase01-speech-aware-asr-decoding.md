# ADR 0020: Phase01 Speech-Aware ASR Decoding

Date: 2026-08-31

## Status

Accepted

## Context

Phase01 previously used amplitude-based FFmpeg silence detection and a
12-second fixed fallback. Continuous music or noise could therefore produce
fixed chunks, while real speech could be cut mid-sentence. The pinned NVIDIA
Parakeet Vietnamese CTC model also ran without the 4-gram language-model beam
decoder supplied with its checkpoint. Canonical transcript rows did not carry
enough acoustic evidence to distinguish useful speech from repeated or
low-confidence text.

Notebook 01 runs on Python 3.13 T4-class workers with limited RAM, VRAM, and
scratch space. ASR changes must keep memory bounded, remain reproducible across
workers, and fail explicitly rather than silently reducing decoder quality.

## Decision

Production NeMo ASR uses this graph:

```text
bounded mono 16 kHz audio stream
  -> Silero ONNX voice activity detection
  -> merge nearby speech and pad boundaries
  -> split only speech longer than 30 seconds
  -> Parakeet CTC inference, one segment at a time
  -> pinned 4-gram KenLM + lexicon Flashlight beam search
  -> acoustic and lexical quality gate
  -> canonical accepted rows + separate diagnostics
```

VAD is speech-aware rather than amplitude-only. Detection uses bounded,
overlapping audio blocks, merges short gaps, and pads endpoints. Thirty seconds
is a hard resource cap, not the primary segmentation rule. Only forced splits
receive a small overlap; repeated boundary tokens are removed deterministically.

The `.nemo`, binary 4-gram language model, and lexicon are pinned by revision
and SHA-256. Flashlight uses the current NeMo 2.7.3 nested decoder contract with
beam size 64. Its CPython 3.13 Linux x86-64 wheel is built outside the notebook,
repaired into a self-contained manylinux wheel, stored with a checksummed
manifest in the checkpoint dataset, and installed by Notebook 01 before
preflight. Greedy decoding is not a production fallback.

ASR extracts and transcribes one temporary segment at a time and releases it
before continuing. The post-decoding gate records CTC blank ratio, mean
non-blank posterior, normalized entropy, text density, character rate, and
repetition reasons. Rejected candidates remain diagnostic evidence but are not
published as canonical transcripts. Thresholds are conservative so short
speech, names, and lyrics are not rejected merely for lacking sentence-like
semantics.

The canonical Flashlight transcript is aligned without changing decoder
authority. With NeMo 2.7.3, `preserve_alignments=True` retains the same
inference's T-by-V CTC acoustic matrix; returned beam hypotheses no longer
retain the winning token sequence after model post-processing. System1
therefore retokenizes the canonical text with NeMo's model-aware tokenizer
utility, runs deterministic CTC Viterbi alignment over the retained matrix,
and derives timestep duration from preprocessor stride times encoder
subsampling. `compute_timestamps=False` remains required for Flashlight.

Accepted segments publish `asr_words_v1`. Faster-Whisper, when explicitly
selected, must enable provider word timestamps and normalize them to the same
canonical contract. A deterministic alignment/reconstruction failure is
terminal; production never reruns greedy decoding or falls back to copying a
whole segment into every overlapping interval.

## Alternatives Considered

1. Keep fixed 12-second chunks. Rejected because they discard natural speech
   boundaries and context.
2. Keep FFmpeg `silencedetect` as the primary detector. Rejected because loud
   music and quiet speech are not reliably classified by amplitude.
3. Compile Flashlight in every notebook. Rejected because compiler downloads,
   RAM pressure, and unpinned build inputs weaken worker reproducibility.
4. Fall back to greedy decoding when Flashlight fails. Rejected because output
   quality would silently differ between workers.
5. Let an LLM delete transcripts that appear meaningless. Rejected because
   names, short utterances, and song lyrics remain useful retrieval evidence.

## Consequences

Positive:

- Segment boundaries follow speech and natural pauses.
- The supplied 4-gram language model participates in production decoding.
- Canonical transcripts exclude acoustically or lexically suspect candidates
  while retaining auditable diagnostics.
- Streaming detection and batch-size-one inference keep memory bounded.
- Decoder identity and artifact checksums participate in configuration and
  checkpoint identity.
- Word-level text attribution prevents full-segment leakage across shot and
  scene boundaries while preserving many-to-many segment links as provenance.

Tradeoffs:

- Python 3.13 workers require a separately built and uploaded native wheel.
- VAD and quality thresholds require calibration against real Vietnamese speech,
  music, and noisy videos.
- A missing or incompatible decoder artifact now fails preflight instead of
  allowing lower-quality greedy output.
- ASR and downstream transcript-link checkpoints must be recomputed to publish
  word-aligned artifacts; shots, keyframes, OCR and captions remain reusable.

## Follow-Up

- Upload the pinned wheel and manifest to the configured checkpoint dataset.
- Run a real one-video smoke on a T4 and review every rejected ASR diagnostic.
- Calibrate only from observed false accepts and false rejects, then run a
  heterogeneous small batch before the full dataset.
