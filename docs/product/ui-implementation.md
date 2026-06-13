# UI Implementation

## Status

Canonical UI implementation contract. Dense technical UI; no marketing surface.

## Main Layout

```text
Top bar
  query input, query type, clue mode, dataset health, runtime status

Left panel
  query sessions, clue history, notes, pinned candidates

Main panel
  result grid of candidate keyframes

Right panel
  selected candidate inspector, video player, nearby keyframes, evidence

Bottom panel or modal
  export preview, validation warnings, agent run panel/logs
```

## Candidate Card Fields

Every result card should show:

- thumbnail;
- `video_id`;
- `frame_id`;
- `timestamp_sec`;
- final score;
- modality/evidence badges;
- validation warnings if any;
- quick actions: inspect, pin, similar, open video context.

## Candidate Inspector

The inspector should show:

- selected keyframe image;
- video player seeked to `timestamp_sec`;
- nearby keyframe strip from the same video;
- evidence blocks for caption, OCR, ASR, objects, and metadata;
- score component breakdown;
- save/update candidate actions.

## Query Session UX

- Session switcher is always visible.
- Users can create independent sessions without authentication.
- Optional nickname/client label may be stored locally for attribution.
- Clue mode toggle supports `current_only` and `accumulated`.
- Pinned candidates persist across searches within the session.

## Candidate Tray

The candidate tray stores session-scoped saved results and supports:

- normal frame candidates;
- Q&A answer editing;
- TRAKE ordered sequence editing;
- export preview;
- validation warnings before copy/export.

## Agent Run Panel

The same UI must render automatic mode:

- start/reuse an agent run in the active Query Session;
- show status, elapsed time, max steps, and max runtime;
- show tool calls, search summaries, and chosen candidates;
- allow accept, edit, reject, or cancel;
- keep agent evidence visible beside normal candidate evidence.

## Validation Warnings

UI should surface warnings such as:

- missing modality evidence;
- candidate not reviewed;
- TRAKE sequence not ordered;
- answer text missing for Q&A;
- dataset health not ready;
- export fields incomplete.

## Performance Rules

- Lazy-load thumbnails.
- Virtualize large result grids.
- Show first results as soon as possible.
- Keep search and rerank asynchronous.
- Load video only when a candidate is inspected.
- Avoid blocking the whole UI on agent progress or export validation.
