# ADR 0023: Phase01 And Phase02 Model Stack Revision

Date: 2026-10-25

## Status

Accepted. Amended by ADR 0025 (2026-10-26): captions run in a separate pass
over worker packages, not inside the worker. Models fixed on 2026-10-25 from the Kaggle trials recorded in
`docs/plans/active/system1-pipeline-simplification.md` (Trial Results):

| Stage | Model |
| --- | --- |
| Image embedding | `google/siglip2-so400m-patch14-384` (CLIP and BEiT3 not kept) |
| Text embedding | `intfloat/multilingual-e5-large` |
| ASR | `khanhld/chunkformer-ctc-large-vie` |
| OCR | EasyOCR text detection (GPU) + VietOCR `vgg_transformer` recognition, with noise and repeat filtering |
| Captions | `Qwen/Qwen3-VL-4B-Instruct`, xgrammar JSON-schema constrained, batch 8; `visible_text` kept as secondary OCR evidence |

Revisions and checksums are pinned in `system1/configs/models.yaml` during
implementation. Captions remain subject to the evaluation-set check in
decision 4.

Supersedes ADR 0018 and ADR 0020, and the model choices in ADR 0015.

## Context

Evidence from the 2026-08-25 to 2026-08-27 production run on
`canonical_release_v001` (77 videos attempted, 56 completed):

- About 37 GPU-minutes per video, or roughly 540 GPU-hours for 873 videos.
- OCR (Vintern-1B, prompt `keyframe_ocr_v2`): 170 of 195 rows for `L30_V030`
  were the prompt placeholder `<every visible line, joined by spaces>`, and the
  OCR gate reported zero failures.
- ASR (Parakeet CTC 0.6B Vietnamese with Flashlight 4-gram decoding): frequent
  broken syllables. The Flashlight decoder needs a project-built wheel and a
  pinned Python 3.13 runtime.
- Shot captions: eight separate generations per shot (caption, objects,
  actions, and visible-text summary, each in Vietnamese and English) because
  prompt-only JSON output was unreliable. Generation is unconstrained
  (`model.generate` followed by `json.loads`).
- Phase02 has no real embedding provider. `features/providers.py` only has a
  4-dimensional hash-based mock, and the visual index is `IndexFlatL2` or a
  JSON stub.

## Decision

1. **Visual embeddings (required).** Add real providers for SigLIP2 and BEiT3,
   with CLIP as a baseline. BEiT3 queries are translated to English first;
   SigLIP2 accepts Vietnamese directly. Vectors are L2-normalized and indexed
   for inner-product search. One or two indexes are kept based on measured
   retrieval quality.
2. **ASR.** Replace Parakeet plus Flashlight with ChunkFormer-large-vie or
   PhoWhisper-large, chosen by trial on Batch 1 videos. Remove the Flashlight
   runtime artifact and the Python 3.13 pin.
3. **OCR.** Replace VLM OCR with a dedicated OCR model (PP-OCR v5 or v6 with
   Vietnamese recognition), run only on keyframes where text is detected.
   Deduplicate identical text across adjacent keyframes and drop text repeated
   across most of a video (channel logos and watermarks).
4. **Captions (optional stage).** One generation per shot or sub-shot, in
   Vietnamese only, with JSON-schema constrained decoding (xgrammar or
   lm-format-enforcer with transformers, or vLLM structured outputs). Candidate
   models: Qwen3-VL-4B or 2B. The stage is kept only if evaluation shows it
   improves retrieval over embeddings alone. Prompts contain no `<...>`
   placeholder text.
5. **Text retrieval (hybrid).** Text evidence is searched both lexically and
   by meaning:
   - OCR: mainly lexical (SQLite FTS5, `unicode61` tokenizer), with an
     additional diacritic-free column for OCR and typing errors.
   - ASR: transcript chunked into 10 to 30 second windows aligned to shots or
     sub-shots; indexed lexically and with a multilingual text embedding.
   - Captions: mainly text embedding, plus lexical.
   The text embedding model must handle Vietnamese and run at query time in
   System 2. Candidates: BGE-M3, multilingual-e5-large, Qwen3-Embedding-0.6B,
   chosen by trial. Result lists from image embeddings, text embeddings, and
   lexical search are combined with Reciprocal Rank Fusion before the temporal
   window of ADR 0021 is applied.
6. Model IDs, revisions, and checksums remain configuration and provenance
   values in `system1/configs/models.yaml`.

## Alternatives Considered

1. Keep the current stack and tune prompts. Rejected: the cost and the OCR and
   ASR quality problems are structural.
2. Use organizer CLIP features as the production visual index. Rejected: ADR
   0015 keeps one self-generated evidence lineage. Organizer data may be used
   only as an evaluation baseline.

## Consequences

Positive:

- Visual search, the main retrieval signal, gets a real implementation.
- Fewer heavy models and far fewer generations per video.
- No custom-built decoder wheel or Python version pin for ASR.

Tradeoffs:

- Trial runs on Kaggle are required before models are fixed.
- Existing Phase01 checkpoints are not reusable.

## Follow-Up

- Run the model trials and record measured quality and time per video.
- Update `system1/configs/models.yaml`, providers, and dependencies.
