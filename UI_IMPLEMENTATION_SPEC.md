# UI Spec

## Goal

Fast browser UI for multimedia retrieval.

The UI should optimize for:

- search speed;
- thumbnail scanning;
- video/timeline inspection;
- candidate selection;
- progressive query reveal;
- interactive manual control;
- automatic agent review;
- export validation.

Keep it dense and practical. Do not build a marketing-style page.

## Main Layout

```text
Top bar
  query input, mode, system status

Left panel
  query sessions, clues, pinned candidates

Main panel
  result grid of frames

Right panel
  selected candidate, video player, timeline, evidence

Bottom / modal
  export preview, validation, agent/logs when needed
```

## Core Screens

### Search

- query input;
- query type selector: TKIS, Q&A, TRAKE, VKIS;
- current clue vs accumulated clue toggle;
- result grid with thumbnails;
- group/diversify by video option.

### Candidate Inspector

- selected frame/keyframe;
- video player seeked to timestamp;
- nearby keyframe strip;
- evidence: objects, OCR, ASR, caption, metadata;
- save candidate button.

### Candidate Tray

- saved candidates;
- edit answer for Q&A;
- frame sequence editor for TRAKE;
- CSV row preview;
- validation warnings.

### Progressive Reveal Session

- add new clue batch;
- keep previous clues;
- search current-only or accumulated clues;
- pin candidates across batches.

### Automatic Agent Run

- enter or reuse query session;
- run agent;
- show route/classification;
- show tool calls and evidence used;
- show chosen candidates;
- allow human to accept, edit, or reject.

## Candidate Card

Each card should show:

- thumbnail;
- video id;
- frame id;
- timestamp;
- score;
- evidence badges;
- quick actions: inspect, pin, similar.

## Performance UI Rules

- Lazy-load thumbnails.
- Render only visible grid items.
- Show first results as soon as possible.
- Do not block UI during search or rerank.
- Load video only after candidate click.

## Keyboard Shortcuts

Minimum useful shortcuts:

```text
/       focus search
Enter   run search
j/k     move candidate selection
o       open inspector
p       pin candidate
s       save candidate
e       open export/validation
Esc     close modal/inspector
```

## Visual Style

Use a simple dark technical interface:

- compact panels;
- clear thumbnails;
- readable metadata;
- restrained colors;
- no decorative hero sections;
- no unnecessary animations.
