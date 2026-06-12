# Search Fusion and Evidence

## Status

Canonical search-fusion specification for System 2. Derived from `SPEC.md`.

## Retrieval Core Overview

```text
Query
-> Query Understanding
-> Retrieval Strategy Planner
-> Visual / Caption / OCR / ASR / Object / Metadata search
-> Candidate Fusion
-> Optional Top-K reranking
-> Evidence Builder
-> Ranked Results
```

## Search Modalities

### Visual Search
- Input: text-to-visual embedding query, selected keyframe, optional image embedding.
- Output: ranked keyframes.
- Backend: FAISS with CLIP/SigLIP/EVA-CLIP/provided embeddings.

### Caption Search
- Input: text query.
- Output: keyframes or segments with matching captions.
- Backend: SQLite FTS5 for MVP; optional text embeddings later.

### OCR Search
- Input: text expected on screen.
- Output: keyframes with OCR matches.
- Best for signs, slides, names, numbers, and logos.

### ASR Search
- Input: words or concepts expected in speech.
- Output: video segments and nearby keyframes.
- Best for interviews, speeches, narration, and answer extraction.

### Object / Concept Search
- Input: object labels or concepts.
- Output: keyframes containing matching objects/concepts.

### Metadata Search
- Input: title/channel/description/source clues.
- Output: videos or keyframes related to metadata matches.

## Result Score Model

Every candidate should preserve per-modality scores.

```json
{
  "video_id": "L01_V028",
  "frame_id": 25300,
  "score": 0.842,
  "scores": {
    "visual": 0.88,
    "caption": 0.72,
    "ocr": 0.0,
    "asr": 0.51,
    "object": 0.69,
    "metadata": 0.2
  }
}
```

## Strategy-based Fusion

Fusion weights must be configurable per strategy.

```yaml
strategies:
  hybrid_default:
    visual: 0.35
    caption: 0.25
    ocr: 0.10
    asr: 0.15
    object: 0.10
    metadata: 0.05

  visual_heavy:
    visual: 0.55
    caption: 0.20
    ocr: 0.05
    asr: 0.05
    object: 0.15
    metadata: 0.00

  speech_heavy:
    visual: 0.15
    caption: 0.15
    ocr: 0.05
    asr: 0.55
    object: 0.05
    metadata: 0.05
```

## Result Diversification

The system should avoid returning many near-duplicate frames from the same moment.

### Allowed Diversification Rules
- group by video
- group by shot/segment
- keep top N frames per video
- minimum frame distance between results
- grouped and ungrouped display modes

## Reranking

Reranking is optional and must stay top-K only.

### Possible Rerankers
- text cross-encoder over captions/transcripts
- LVLM verification on a small frame set
- rule-based evidence score
- agent-generated verification summary

Reranking must always be controllable to protect latency.

## Evidence Builder

Each result should expose a compact evidence object.

```json
{
  "caption": "A person wearing a white protective suit stands inside a cave.",
  "ocr": "",
  "asr": "... interview in French about cave engineering ...",
  "objects": ["person", "helmet", "cave"],
  "metadata": {
    "title": "...",
    "source": "..."
  },
  "agent_reasoning": "Optional short explanation."
}
```

Evidence should be lazy-loaded when practical.
