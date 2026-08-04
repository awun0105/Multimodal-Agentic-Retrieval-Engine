# Query Workflows

## Status

Canonical workflow model for human and agent use. One Web UI supports all workflows through Query Sessions.

See `docs/product/requirements-truth-set.md` for confirmed preliminary
requirements, later-round assumptions, and unknowns.

## Shared Query Session Model

A Query Session stores:

- query type: `tkis`, `qa`, `trake`, or optional later-round `vkis` / `hybrid`;
- current clue batch;
- accumulated clues;
- selected clues enabled for a search;
- search history;
- notes;
- pinned candidates;
- candidate validation, answer draft, and submission state;
- submission history for the active question/session;
- optional agent runs.

Final-round operation uses public-screen progressive reveal: competitors look at the screen, manually enter clues into their team system, and each question session is separate. In a session, clue batches are revealed one after another and earlier batches disappear from the public screen.

Progressive reveal supports two modes:

- `current_only`: search only the newest clue batch.
- `accumulated`: search the merged clue history for the session.

Pinned candidates persist across clue batches.

The confirmed preliminary query types are Textual KIS, Q&A, and TRAKE. VKIS
and generic hybrid search remain useful later-round or internal exploration
modes, but they are not part of the current preliminary-ready acceptance gate.

## Textual KIS

Goal: find a frame from natural-language clues.

Flow:

1. Create or reuse a Query Session with type `tkis`.
2. Add the current clue batch.
3. Search current-only or accumulated clues.
4. Fuse caption, OCR, ASR, object, metadata, and visual adapters.
5. Inspect evidence and nearby frames.
6. Pin candidates and prepare a task-specific answer draft.
7. Review with teammates before explicit submit.

## Q&A

Goal: answer a question using visual and textual evidence.

Flow:

1. Enter the question and optional clue context.
2. Search with high weight on text evidence and objects when relevant.
3. Inspect candidate evidence.
4. Save a candidate with `answer_text`.
5. Validate answer fields: `video_id`, `frame_id`, `answer_text`.

The UI must support editing answer text after saving a candidate.

## TRAKE

Goal: produce one ranked same-video event sequence with one exact `frame_id` per
query event.

Flow:

1. Split the query into labelled event clauses.
2. Retrieve candidate frames/shots for each event.
3. Join candidates by `video_id` and preserve the query's event labels.
4. Apply chronological constraints only when the query semantics require them.
5. Inspect same-video timeline and refine exact event frame IDs.
6. Prepare `<video_id>, <frame_id_1>, ..., <frame_id_n>` rows for top-100
   review and export.

TRAKE candidates contain one `video_id` and multiple event frame IDs. Any
runtime temporal cache is derived state; System 1 does not publish a canonical
`temporal_search.parquet`.

## VKIS / Video KIS

Status: optional later-round or internal exploration mode, outside the current
preliminary-ready acceptance gate.

Goal: locate a video moment from a visual/video description.

Flow:

1. Describe visual content or remembered scene.
2. Prioritize visual, object, caption, and metadata adapters.
3. Group/diversify results by video when scanning broadly.
4. Inspect video player and nearby keyframe strip.
5. Save the best frame candidate.

## Candidate Selection Behavior

- Candidate cards show score, modality badges, video/frame IDs, timestamp, and warnings.
- Selection never auto-submits; human must inspect and explicitly submit.
- Saving a candidate snapshots score and evidence for later comparison.
- Similar-frame and same-video exploration must preserve the current Query Session.

## Submission Workflow

Final-round submission is expected to use an organizer-provided API, but exact endpoint, auth, payload format, scoring feedback, rate limits, and required notes are unknown.

System 2 must support this requirement at product level:

1. Build a task-type-specific answer draft from one or more candidates.
2. Let the user edit the answer before submission.
3. Show prior submissions for the current question/session.
4. Warn when submitting after previous attempts because wrong submissions may reduce score.
5. Submit only after explicit human action.
6. Store submission request metadata, response metadata, status, timestamp, and actor when available.

The agent may propose or prepare answers, but it must not submit to organizer API without explicit human confirmation.

## Agent Workflow

The agent uses the same Query Session and APIs as the UI:

1. Classify query type.
2. Choose clue mode and retrieval adapters.
3. Run bounded search/refinement steps.
4. Inspect evidence and save candidate proposals.
5. Explain tool calls and rationale.
6. Wait for human accept, edit, or reject.

Agent constraints: bounded steps, bounded runtime, traceable tool calls, no direct raw-file scanning, and no bypass of `MediaStorePort`/repository abstractions.
