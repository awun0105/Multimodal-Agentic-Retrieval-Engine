# Query Workflows

## Status

Canonical query workflow specification for System 2. Derived from `SPEC.md`.

## Principles

- Query workflows run inside the same shared Web UI.
- Query workflows save state into Query Sessions.
- Query workflows share the same retrieval core, evidence builder, and candidate model.
- Current clue, accumulated clues, and selected clues must all be supported.

## Textual KIS

### Goal

Find a target video/keyframe from a natural language description.

### Workflow

```text
User enters clue(s)
-> optional query understanding / clue decomposition
-> hybrid retrieval
-> ranked keyframes/videos
-> inspect keyframe and nearby frames
-> save candidate
-> copy video_id/frame_id
```

### Required Features

- current-clue search
- accumulated-clue search
- selected-clue search
- optional query rewriting
- group-by-video mode
- same-video keyframe browsing

## Q&A

### Goal

Find the target video/keyframe and produce the answer value.

### Workflow

```text
User enters retrieval clue + question
-> retrieve candidate frames/videos
-> inspect evidence and nearby keyframes
-> use answer helper when needed
-> copy video_id, frame_id, answer
```

### Answer Helper Requirements

- free-text answer box
- optional normalization presets:
  - digits only
  - uppercase
  - remove spaces
  - remove accents
  - max-length check
- evidence snippets from OCR, ASR, and captions

## TRAKE

### Goal

Find ordered event frames in one video.

### Workflow

```text
User defines event sequence
-> search broad candidate videos
-> inspect same-video timeline/keyframes
-> choose frame for each event
-> validate order
-> copy TRAKE row
```

### MVP Behavior

- user manually selects frames into a sequence
- system validates same-video and increasing frame order
- optional helper suggests candidate frames per event

## VKIS / Video KIS

### Goal

Find the correct video and matching keyframes when the query is video-oriented.

### Workflow

```text
User enters query
-> retrieve ranked candidate frames
-> group by video
-> inspect same-video keyframes and metadata
-> save likely video/frame candidates
```

### Required Features

- group by video
- top-N per video
- same-video explorer
- candidate diversification

## Progressive Clue Reveal

Query Sessions must support progressive reveal.

### Required State

- clue list ordered by time
- user query history
- pinned candidates
- selected clue subsets
- notes

### Search Modes

- search only current clue
- search accumulated clues
- search selected clues

## Shared Candidate Model

All workflows must reuse the same candidate shape:

```json
{
  "video_id": "L01_V028",
  "frame_id": 25300,
  "score": 0.842,
  "answer": null,
  "trake_frames": null,
  "notes": "...",
  "label": "maybe"
}
```
