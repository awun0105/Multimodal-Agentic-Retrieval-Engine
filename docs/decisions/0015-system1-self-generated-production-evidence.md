# ADR 0015: System 1 Self-Generated Production Evidence

Date: 2026-08-05

## Status

Accepted

## Context

The organizer provides videos, optional metadata, and several support artifacts
created by an organizer baseline. Mixing organizer and project keyframes,
objects, CLIP vectors, frame maps, or media-info into the production pipeline
would create multiple mapping/provenance/model contracts and make quality harder
to reproduce consistently across Batch 1 and future batches.

Notebook 01 also needs fixed production choices for shot detection, ASR,
bilingual captions, scene grouping, summaries, failure behavior, and the
Notebook 02 handoff.

## Decision

System 1 uses official videos and optional organizer metadata only. It
regenerates all derived retrieval evidence. ADR 0016 further requires one
project-owned canonical metadata JSON per video without claiming that the
organizer supplied metadata for every video.

Production Notebook 01 uses TransNet V2, three target keyframes per normal shot
at approximately 20/50/80 percent, faster-whisper large-v3 with automatic
language and VAD, Gemini bilingual strict-JSON shot captions, multimodal Gemini
scene grouping, and Gemini bilingual strict-JSON scene summaries.

Production failures are explicit after bounded retry; mock and silent semantic
fallbacks are prohibited. Valid observed empty states such as a successful
TransNet no-cut result, no audio stream, or no detected speech remain valid.

Notebook 02 uses Notebook 01 keyframes to generate Gemini OCR, configured object
detections, and separate SigLIP and BEiT3 indexes. Exact runtime model IDs remain
configuration/provenance values.

The complete target contract is
`docs/architecture/system1-notebook01-production-pipeline.md`.

## Alternatives Considered

1. Import organizer support artifacts when they validate. Rejected to avoid two
   derived-data lineages and inconsistent model/frame mapping.
2. Use organizer CLIP as a third baseline index. Rejected to keep the release
   focused on the two selected project-generated indexes.
3. Silently degrade failed production providers to mock/full-video output.
   Rejected because valid artifact shape would conceal unusable retrieval
   evidence.
4. Store one caption/summary string with a language tag. Rejected because the
   selected provider contract requires both Vietnamese and English in one
   canonical row per shot/scene.

## Consequences

Positive:

- One reproducible derived-data lineage and frame-ID contract.
- Bilingual retrieval text is explicit rather than inferred.
- Production failures cannot masquerade as successful semantic artifacts.
- SigLIP and BEiT3 can be evaluated and served independently.

Tradeoffs:

- System 1 pays the compute/API cost of regenerating all derived evidence.
- Organizer support artifacts cannot accelerate processing or provide a free
  third baseline.
- Exact Gemini, object detector, SigLIP, and BEiT3 model IDs must be configured
  and captured before a run is reproducible.

## Follow-Up

- Implement production provider adapters and update Notebook 01 configuration.
- Complete production provider output against the migrated bilingual
  Parquet/schema contract and multilingual text-source generation.
- Implement Notebook 02 dual embedding outputs and dual FAISS build.
- Prove one-video, small-batch, then full-Batch-1 execution.
