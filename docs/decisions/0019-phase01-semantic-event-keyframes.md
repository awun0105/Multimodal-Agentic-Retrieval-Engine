# ADR 0019: Phase01 Semantic-Event Keyframes

Date: 2026-08-25

## Status

Accepted

## Context

Phase01 selects mandatory early, middle, and late keyframes from quality-scored
search bands within each TransNet shot. This gives stable basic coverage but a
long shot can contain a short visual event or changed subtitle/lower-third
between those three anchors. Sampling every fixed interval would increase data,
OCR cost, and downstream evidence without guaranteeing new information.

Phase00 already provides exact decoded-frame `pts_time`, and Phase01 already
decodes grouped candidate IDs in one forward video pass. The existing OpenCV
OCR gate also supplies reusable MSER/Canny primitives for a cheap text signal.

## Decision

Mandatory early/middle/late candidate generation and representative selection
remain unchanged and frame-ratio based. A supplemental policy uses exact
`frame_timeline.pts_time` only for temporal coverage probes. Coverage is seeded
by safe-interior start/end and nominal early/middle/late timestamps, then the
largest timestamp gap is bisected until the configured target or probe cap.

Anchor and probe frame IDs are combined before the existing one-pass grouped
decode. Actual selected anchors become the first novelty references. A probe is
eligible only when it has valid existing quality evidence and either:

- its normalized dHash distance is above threshold relative to every retained
  visual reference; or
- it contains plausible text and its masked Canny-edge signature differs from
  every usable retained text reference.

Text disappearance alone is not a trigger. Selection greedily recomputes
novelty after every accepted frame. Ranking uses triggered-signal count,
strongest triggered-signal score, quality, timestamp distance to the nearest
actual anchor, and lower frame ID. Configured probe, separation, and output caps
bound cost deterministically.

Accepted rows use `keyframes_v3` role `supplemental` and are always
non-representative. OCR processes them through its existing gate, all their OCR
joins scene evidence, and focused scene review may show every supplemental
image. Shot captioning remains one representative image per shot; scene-summary
image sampling also remains representative-only. Semantic sampling stays in
the `keyframes` checkpoint stage and its versioned media config participates in
that stage fingerprint.

## Alternatives Considered

1. Fixed-interval persisted keyframes. Rejected because static shots would
   produce many duplicate artifacts and downstream OCR work.
2. Caption every probe with Qwen or OCR every probe with Vintern. Rejected
   because probes must remain cheap and selected images alone enter heavy model
   stages.
3. Use CLIP, object detection, or a trained event detector. Deferred to a later
   measured improvement; V1 uses deterministic OpenCV signals already supported
   by the runtime.
4. Relabel supplemental frames as early/middle/late. Rejected because it would
   corrupt role semantics and overwrite repeated role evidence.

## Consequences

Positive:

- Short-lived visual and text events between anchors can enter Phase01 evidence.
- Static long shots remain bounded and normally add no keyframes.
- VFR videos use decoded timestamps rather than estimated frame spacing.
- Diagnostics explain coverage caps, novelty, dedup, and every keep/drop result.

Tradeoffs:

- Long shots decode more temporary candidate frames and run cheap CPU OpenCV
  descriptors on them.
- dHash and masked-edge thresholds require real-video review and may miss
  object-only changes that preserve global appearance.
- `keyframes_v3` invalidates the keyframe stage and its semantic downstream
  stages for checkpoints created under the previous contract.

## Follow-Up

- Run the one-video and small-batch real-provider acceptance sequence and review
  supplemental precision/recall plus output-size growth.
- Consider object-change detection only after measured misses justify the added
  dependency and compute cost.
