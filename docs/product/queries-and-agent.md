# Queries And Agent

## Status

Canonical behavior contract for query handling and automatic mode.

## Query Types

| Type | User Intent | Primary Outputs |
| --- | --- | --- |
| Textual KIS (`tkis`) | Find a frame from text clues. | `video_id`, `frame_id`, evidence. |
| Q&A (`qa`) | Answer a question with supporting frame/evidence. | `video_id`, `frame_id`, `answer_text`, evidence. |
| TRAKE (`trake`) | Build an ordered frame sequence. | ordered `(video_id, frame_id)` sequence. |
| VKIS (`vkis`) | Find a video moment from visual/video description. | `video_id`, `frame_id`, evidence. |

## Clues

Each Query Session keeps current and accumulated clues. Searches must explicitly record which mode was used:

- `current_only`: newest clue batch only.
- `accumulated`: all active clue batches.
- `selected`: user-selected subset when the UI adds clue selection.

## Agent Contract

The agent is not a separate product. It is an automation layer over the same retrieval, evidence, session, candidate, and media APIs as the Web UI.

Required constraints:

- Use the same API payloads as human UI workflows.
- Keep every tool call traceable in `agent_steps`.
- Respect `max_steps` and `max_runtime_sec`.
- Save proposals as normal candidates in the active Query Session.
- Include evidence and score components for every selected candidate.
- Allow human accept, edit, reject, or cancel.
- Never read raw dataset paths directly during live retrieval.

## Minimum Agent Tools

| Tool | Purpose |
| --- | --- |
| `search` | Run hybrid retrieval with query type, clue mode, filters, and top-K. |
| `get_keyframe` | Inspect one keyframe payload. |
| `get_evidence` | Fetch caption/OCR/ASR/object/metadata evidence. |
| `get_neighbors` | Inspect nearby keyframes in the same video. |
| `save_candidate` | Persist a proposed candidate. |
| `update_candidate` | Edit answer text, TRAKE sequence, notes, or validation state. |

## Output Shape

Agent output must include:

- route/classification used;
- clue mode;
- searches performed;
- inspected candidates;
- chosen candidates;
- evidence summary;
- unresolved warnings;
- human next action.
