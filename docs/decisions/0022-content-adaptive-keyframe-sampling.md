# ADR 0022: Content-Adaptive Keyframe Sampling

Date: 2026-10-25

## Status

Accepted

Supersedes the per-shot keyframe count limits in ADR 0019.

## Context

Keyframes are selected per shot: early, middle, and late, plus at most two
supplemental keyframes (`max_supplemental_keyframes_per_shot: 2`,
`max_probe_candidates_per_shot: 24` in `system1/configs/media.yaml`). A video
recorded as one continuous shot therefore gets at most five keyframes,
regardless of length. Long panning or vlog shots have the same problem. Moments
that are not near a sampled keyframe cannot be retrieved.

## Decision

Keyframe density follows visual change, not the number of shots:

1. Generate candidates at a minimum rate of one per N seconds across every
   shot (N is configuration, initially 1 to 2 seconds).
2. Keep a candidate only when it differs enough from the last kept keyframe
   (difference hash or image embedding distance). Static content keeps few
   keyframes; changing content keeps many.
3. Split long shots into sub-shots when content drifts past a threshold from
   the sub-shot start or a maximum length is reached (initially 10 to 15
   seconds). Captions and OCR run per sub-shot.
4. TransNetV2 shot boundaries remain: no keyframe spans a cut, and keyframes
   avoid transition frames.
5. A shot or sub-shot that yields no valid candidate is skipped and logged. It
   does not fail the video.

## Alternatives Considered

1. Raise the per-shot supplemental limit. Rejected: still couples density to
   shot count and fails for one-shot videos.
2. Fixed-rate sampling without deduplication. Rejected: large storage and
   embedding cost on static content.

## Consequences

Positive:

- One-shot and long-shot videos become searchable across their full length.
- Keyframe count tracks content change.

Tradeoffs:

- Keyframe count per video varies widely; storage and embedding cost must be
  measured on real videos.
- Exact thresholds need tuning on Batch 1 samples.

## Follow-Up

- Implement in `system1/src/system1/keyframes/` under
  `docs/plans/active/system1-pipeline-simplification.md`.
- Compare keyframe counts with the organizer baseline (about 200 per video).
