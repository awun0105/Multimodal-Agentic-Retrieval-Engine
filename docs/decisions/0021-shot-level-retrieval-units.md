# ADR 0021: Shot-Level Retrieval Units Without Scene Grouping

Date: 2026-10-25

## Status

Accepted. Decision 3 amended by ADR 0026 (2026-10-26): scenes return as a
deterministic grouping of shots with a text-only summary; decisions 1 and 2
stand.

Supersedes ADR 0014 and the scene-grouping and scene-summary parts of ADR 0015
and ADR 0018.

## Context

Phase01 partitions shots into scenes with repeated Qwen2.5-VL-7B boundary
judgements (primary, focused, consistency, and degenerate review) and then
summarizes each scene with four prompts. The 2026-08-27 production run on
`canonical_release_v001` showed:

- scene summaries that mostly repeat the first shot caption (for example
  `L30_V030`);
- the highest GPU cost per video among Phase01 stages;
- about 1,800 lines in `system1/src/system1/scenes/` plus scene handling in
  `phase01/production.py`, a manual-review flow, and a quality guard.

Competition answers are a `video_id` and a frame inside the answer range, not a
scene. A fixed scene partition also makes boundary errors permanent: a query
that spans two wrongly separated scenes cannot match.

Strong AIC 2025 systems on the same Batch 1 data retrieve at keyframe and shot
level without scene grouping.

## Decision

1. The shot, and the keyframes inside it, are the preprocessing units. Phase01
   no longer produces `scenes`, `scene_transcript_links`, or `scene_summaries`.
2. Multi-shot context is computed at query time by System 2 with a temporal
   window around each candidate keyframe (for example, aggregating scores of
   keyframes within plus or minus T seconds). This covers interleaved A-B-A
   shot patterns and lets T vary per query without reprocessing.
3. If evaluation later shows the temporal window is insufficient, scenes may be
   reintroduced only as a deterministic, model-free step: shot-embedding
   linking over the previous K shots combined with transcript topic
   segmentation. VLM scene judgement and VLM scene summaries are not
   reintroduced.

## Alternatives Considered

1. Keep VLM scene grouping and fix its quality. Rejected: highest cost, low
   observed value, and permanent boundary errors.
2. Replace it immediately with embedding-based scene linking. Deferred until an
   evaluation set shows that query-time windows are not enough.

## Consequences

Positive:

- Removes the most expensive Phase01 stages and their review machinery.
- Query-time context adapts per query and has no boundary errors.

Tradeoffs:

- System 2 must implement temporal-window scoring (the `mvp-app` temporal
  window and TRAKE solver are the starting point).
- Existing scene tables and scene-summary text are dropped from new releases.

## Follow-Up

- Remove scene stages from `system1/configs/phase01.yaml`, `phase01/production.py`,
  `scenes/`, schemas, and tests under
  `docs/plans/active/system1-pipeline-simplification.md`.
- Implement temporal-window scoring in System 2.
