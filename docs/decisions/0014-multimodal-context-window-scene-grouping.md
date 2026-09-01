# ADR 0014: Multimodal Context-Window Scene Grouping

Date: 2026-08-05

## Status

Accepted. Provider/runtime selection was amended by ADR 0018.

## Context

Notebook 01 must partition each video's ordered shots into useful semantic
scenes. Independent adjacent-shot comparisons lose wider event context and can
mistake camera-angle changes for scene boundaries. Free-form VLM scene output,
on the other hand, would let a model fabricate IDs, frame ranges, or incomplete
partitions that violate the app-ready contract.

The repository already requires scenes to derive from consecutive shots,
canonical bilingual shot captions, ASR/transcript evidence, representative
images, and timeline continuity. It also requires deterministic IDs and
frame-safe mapping.

## Decision

Production Phase01 scene grouping uses multimodal context-focus windows over
ordered shots. A provider judges only Boolean boundaries between adjacent shots
using representative images, canonical shot captions, ASR text, and timeline
context. Overlapping votes are aggregated deterministically; ambiguous gaps and
inconsistent regions receive bounded follow-up review.

Package code, not the provider, constructs and validates the complete scene
partition, deterministic scene IDs, frame/time ranges, counts, and mappings.
The initial provider adapter is Gemini with its exact model and runtime settings
supplied by configuration. Provider failure after bounded retry fails the
production video; it does not trigger a silent semantic fallback.

The complete canonical design is
`docs/architecture/system1-scene-grouping.md`.

Provider amendment, 2026-09-01: the Gemini adapter above records the initial
implementation choice, not the current production runtime. ADR 0018 governs
provider lifecycle. Current production uses Qwen2.5-VL as semantic primary and
the pinned Vintern-3B-R local model as its exclusive sticky fallback. The
scene-grouping algorithm and Python partition authority in this ADR are
unchanged.

## Alternatives Considered

1. Judge every adjacent pair independently. Rejected because it lacks enough
   context for conversations, montage-like angle changes, and returning camera
   views.
2. Use only caption/transcript embeddings and fixed similarity thresholds.
   Rejected as the sole production path because strong visual setting changes
   and multimodal contradictions would be lost.
3. Let a VLM directly return complete scene ranges. Rejected because IDs,
   ranges, coverage, and partition consistency must remain deterministic package
   behavior.
4. Emit one scene per video on provider failure. Rejected for production; one
   scene is valid only when a successful judgement finds no scene boundary.

## Consequences

Positive:

- Boundary decisions use wider multimodal context.
- Overlap and second-pass review reduce dependence on one provider call.
- All canonical ranges and mappings remain deterministic and testable.
- Provider failures cannot masquerade as a successful scene partition.

Tradeoffs:

- Contact sheets and overlapping windows increase preprocessing cost.
- Prompt, schema, model, and grouping configuration require versioned cache
  invalidation and provenance.
- Quality must be proven with behavioral fixtures and a real Batch 1 rehearsal,
  not inferred from valid JSON alone.

## Follow-Up

- Implement the scene-grouping modules and fake-judge unit tests in Phase01.
- Keep provider/runtime selection synchronized with ADR 0018 and production
  config.
- Validate costs, latency, retry behavior, and grouping quality on a Batch 1
  slice before full-dataset processing.
