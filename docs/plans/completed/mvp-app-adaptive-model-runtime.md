# Execution Plan: MVP App Adaptive Model Runtime

Date: 2026-08-19

## Status

Completed

## Outcome

Use a multilingual CLIP-aligned text encoder for direct Vietnamese and English
search, offer optional Vietnamese-to-English NLLB deep search, and adapt model
device/precision/loading to CPU and CUDA without changing the existing search,
FAISS, filtering, pagination, or API structure.

## Context

- `mvp-app/clip.py`: runtime text embedding and release-build image embedding.
- `mvp-app/translation.py`: optional query translation.
- `mvp-app/app.py`: runtime construction and startup loading.
- `mvp-app/database_utils.py`: model configuration defaults.
- `mvp-app/tools/build_release.py`: compatible OpenAI CLIP image embeddings.
- `mvp-app/tests/`: model, query-flow, startup, and runtime contracts.

## Scope

In scope:

- Runtime text model `sentence-transformers/clip-ViT-B-32-multilingual-v1`.
- Lazy translation model `facebook/nllb-200-distilled-600M` from Vietnamese
  (`vie_Latn`) to English (`eng_Latn`).
- CUDA FP16 and CPU FP32 for both model adapters.
- Startup preload of only the multilingual text encoder.
- Preserve the compatible OpenAI CLIP ViT-B/32 image encoder for release
  validation/building without loading it in the search runtime.

Out of scope:

- Rebuilding the existing FAISS release.
- Quantization, ONNX/OpenVINO conversion, model eviction, or multi-GPU routing.
- Changing search/filter/pagination semantics.

## Approach

Keep the existing controller and search mechanism. Adapt `CLIPSearcher` so its
runtime text path uses SentenceTransformers while its release-only image path
remains separately lazy. Adapt `QueryTranslator` to NLLB language tokens,
device, and dtype. Preload the text path in runtime construction and leave the
translator unloaded until the first enabled translation.

## Risks And Recovery

- The multilingual model is text-only; image embeddings must remain produced
  by the original compatible CLIP image encoder.
- NLLB-600M is still large: lazy loading avoids startup RAM/VRAM use but its
  first deep-search call has a substantial load/download cost.
- NLLB is CC-BY-NC-4.0 and its model card says it is a research model, not a
  production deployment model; document this limitation.
- Recovery is a focused revert of model adapters/configuration; release data is
  immutable and no migration is performed.

## Progress

- [x] Inspect current model, runtime, release, and test contracts.
- [x] Verify upstream model revisions, architecture, output dimension, and
  NLLB language codes.
- [x] Adapt model loaders and query flow.
- [x] Update configuration, dependencies, docs, and tests.
- [x] Run focused/full checks and real CPU/GPU-available runtime probes.

## Decisions

- 2026-08-19: Pin multilingual CLIP revision
  `58edf8cada9e398793dca955574a48cbb7f18be2` and NLLB revision
  `f8d333a098d19b4fd9a8b18f94170487ad3f821d`.
- 2026-08-19: Preserve the existing OpenAI CLIP image encoder only for offline
  release validation because the requested multilingual model maps text into
  that image space but does not itself encode images.
- 2026-08-19: The visible checkbox remains authoritative: off sends the
  original text directly to multilingual CLIP; on translates with NLLB first.

## Validation

- Focused proof: model/device/lazy-load/query-flow tests passed as part of the
  51-test MVP suite; focused Ruff passed for all changed runtime behavior and
  tests.
- Integration or end-to-end proof: the real release was searched on a Quadro
  T2000. Startup loaded only multilingual CLIP in FP16; direct Vietnamese search
  kept NLLB unloaded; deep search lazy-loaded NLLB in FP16, translated `con
  chim` to `The bird.`, and passed that text to a 512-dimensional CLIP vector.
  Both models used about 1.45 GiB allocated VRAM. A forced-CPU probe loaded both
  models in FP32, produced 512-dimensional vectors, translated correctly, and
  reached about 3.64 GiB peak RSS.
- Repository-required checks: `51 passed`, focused Ruff passed, Python compile
  passed, `git diff --check` passed, and Makefile dry-runs passed. Full-tree Ruff
  retains six pre-existing findings in release/database tooling and unrelated
  test import ordering.

## Result

Implemented the requested adaptive runtime without changing the existing FAISS
release or search/filter/UI callback architecture. Fast search directly embeds
Vietnamese or English with multilingual CLIP. Deep search lazy-loads NLLB,
translates Vietnamese to English, and embeds the translated text with the same
multilingual model. Runtime startup does not load NLLB or the release-only image
encoder. Known limitations are NLLB's 3.1 GiB cached checkpoint, roughly 3.64
GiB observed CPU process footprint with both models, first-use download/load
latency, and the upstream CC-BY-NC research-only deployment caveat. The legacy
`langid` detector is also initialized only if the legacy auto-language endpoint
is actually used.
