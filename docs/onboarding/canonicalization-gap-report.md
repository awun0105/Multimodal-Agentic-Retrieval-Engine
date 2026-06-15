# Canonicalization Gap Report

## Status

Resolved by canonical full-replace pass on 2026-06-13.

## Summary

Canonical docs under `docs/architecture/`, `docs/product/`, and `docs/decisions/` are now intended to be sufficient for implementation planning without reading archived source inputs.

This file no longer claims that no gaps were ever found. A real gap was discovered after the root data-contract draft was added, and this pass resolves it.

## Gaps Found And Resolved

1. `keyframe_id` conflict
   - Old canonical/runtime wording still showed underscore-like examples.
   - Resolved to `keyframe_id = "{video_id}:{frame_id}"` everywhere canonical.

2. `legacy video-name field` vs `video_id`
   - Old source material used both terms.
   - Resolved to `video_id` for DB/API/docs; `legacy video-name field` is legacy wording only.

3. Logical `data/` tree vs physical roots
   - Some older text implied media/runtime files lived inside repo `data/` paths.
   - Resolved to `${AIC_DATA_ROOT}` and `${AIC_RUNTIME_ROOT}` as physical roots; `data/` examples are logical only.

4. Incomplete canonicalization of product/runtime details
   - Retrieval adapters, fusion, agent constraints, UI card fields, validation warnings, and dataset health payload were not fully captured.
   - Resolved in `docs/product/*.md` and `docs/architecture/system2-retrieval.md`.

5. Incomplete canonicalization of preprocessing details
   - Registration, metadata normalization, thumbnail generation, OCR/ASR/caption/object stages, CLI contract, and validation gate were underspecified.
   - Resolved in `docs/architecture/system1-ingestion.md`.

## Remaining Limitation

Canonical docs are sufficient for implementation planning, but runtime code, app tests, and seed dataset artifacts still do not exist yet. `MVP-0.6` is the next execution milestone.
