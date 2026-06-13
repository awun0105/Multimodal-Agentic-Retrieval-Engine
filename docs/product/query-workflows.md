# Query Workflows

## Status

Canonical workflow model for human and agent use. One Web UI supports all workflows through Query Sessions.

## Shared Query Session Model

A Query Session stores:

- query type: `tkis`, `qa`, `trake`, `vkis`, or `hybrid`;
- current clue batch;
- accumulated clues;
- selected clues enabled for a search;
- search history;
- notes;
- pinned candidates;
- candidate validation/export state;
- optional agent runs.

Progressive reveal supports two modes:

- `current_only`: search only the newest clue batch.
- `accumulated`: search the merged clue history for the session.

Pinned candidates persist across clue batches.

## Textual KIS

Goal: find a frame from natural-language clues.

Flow:

1. Create or reuse a Query Session with type `tkis`.
2. Add the current clue batch.
3. Search current-only or accumulated clues.
4. Fuse caption, OCR, ASR, object, metadata, and visual adapters.
5. Inspect evidence and nearby frames.
6. Pin candidates and copy `video_id,frame_id`.

## Q&A

Goal: answer a question using visual and textual evidence.

Flow:

1. Enter the question and optional clue context.
2. Search with high weight on text evidence and objects when relevant.
3. Inspect candidate evidence.
4. Save a candidate with `answer_text`.
5. Validate export fields: `video_id`, `frame_id`, `answer_text`.

The UI must support editing answer text after saving a candidate.

## TRAKE

Goal: produce an ordered frame sequence, usually within one video.

Flow:

1. Search the first clue or anchor frame.
2. Inspect same-video timeline around the candidate.
3. Add frames to a sequence editor in order.
4. Use object/text/time evidence to validate sequence continuity.
5. Export ordered `(video_id, frame_id)` rows.

TRAKE candidates may contain multiple keyframes instead of one `keyframe_id`.

## VKIS / Video KIS

Goal: locate a video moment from a visual/video description.

Flow:

1. Describe visual content or remembered scene.
2. Prioritize visual, object, caption, and metadata adapters.
3. Group/diversify results by video when scanning broadly.
4. Inspect video player and nearby keyframe strip.
5. Save the best frame candidate.

## Candidate Selection Behavior

- Candidate cards show score, modality badges, video/frame IDs, timestamp, and warnings.
- Selection never auto-submits; human must inspect/copy/export.
- Saving a candidate snapshots score and evidence for later comparison.
- Similar-frame and same-video exploration must preserve the current Query Session.

## Agent Workflow

The agent uses the same Query Session and APIs as the UI:

1. Classify query type.
2. Choose clue mode and retrieval adapters.
3. Run bounded search/refinement steps.
4. Inspect evidence and save candidate proposals.
5. Explain tool calls and rationale.
6. Wait for human accept, edit, or reject.

Agent constraints: bounded steps, bounded runtime, traceable tool calls, no direct raw-file scanning, and no bypass of `MediaStorePort`/repository abstractions.
