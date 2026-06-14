# Requirement Truth Set

## Status

Canonical requirement summary for the current planning phase. This file separates confirmed facts, planning assumptions, unknowns, and out-of-scope items before design or implementation strategy starts.

## Confirmed Requirements

| Area | Requirement | Evidence / Source |
| --- | --- | --- |
| Dataset input | Organizer provides raw video files and per-video metadata JSON files. | Human-provided dataset detail. |
| Video format | Raw videos are `.mp4`. | Human-provided dataset detail. |
| Metadata pairing | Each raw video has one matching metadata JSON with the same filename stem. | Human-provided dataset detail. |
| Canonical `video_id` | Use the raw video filename stem as canonical `video_id`; do not derive it from `watch_url` or YouTube ID. | Human-confirmed decision. |
| Derived artifacts | Organizer does not provide keyframes, embeddings, OCR, ASR, object detections, FAISS indexes, or runtime SQLite. | Human-provided dataset detail. |
| System 1 role | System 1 must generate and validate app-ready retrieval artifacts before System 2 depends on them. | Derived from dataset input constraints. |
| System 2 role | System 2 consumes app-ready artifacts and should not scan raw organizer folders during live retrieval. | Architecture boundary. |
| Runtime target | App must run locally on one machine. | Human-provided runtime requirement. |
| LAN target | App must be hostable on one machine so teammates can use the shared Web UI from browsers over LAN. | Human-provided runtime requirement. |
| Team access | MVP has no auth, no roles, and no submit-permission model; teammate responsibility is handled outside the app. | Human-confirmed scope. |
| Query operation | Competitors look at the public screen and use their own team system to query. | Human-provided final-round detail. |
| Progressive reveal | Each question session is separate; clues are revealed batch-by-batch; earlier batches disappear from the screen. | Human-provided final-round detail. |
| Progressive reveal coverage | The batch reveal model applies to text, video, Q&A, and TRAKE-style questions. | Human-provided final-round detail. |
| Submission workflow | Final-round answers are expected to be submitted through organizer API. | Human-provided final-round detail. |
| Submission review | System 2 must support editable answer drafts, explicit human submit, and per-question/session submission history. | Human-provided final-round detail. |
| Multiple submissions | Multiple submissions may be possible; wrong attempts may reduce score, so submission history and review are required. | Human-provided final-round detail. |
| Internet access | Internet/external services are allowed, including external APIs/models, URL access, and online metadata/thumbnail access. Phones are not allowed. | Human-provided final-round detail. |
| Content domain | Video topics are mainly football and traffic, but video forms are diverse and must not be constrained. | Human-provided domain detail. |

## Planning Assumptions

| Area | Assumption | Revisit Trigger |
| --- | --- | --- |
| Query types | Plan around last-year-style Textual KIS, VKIS / Video KIS, Q&A, and TRAKE until official 2026 rules are released. | Official 2026 rules. |
| FPS | Last-year dataset videos were observed at 25 fps; use 25 fps as expected/default while probing actual FPS per current-year video. | Current-year raw media probe. |
| Local-first reliability | Even though internet is allowed, core retrieval should remain local/LAN-first and artifact-backed so network or provider failures do not break correctness. | Design phase and provider selection. |
| Online providers | External APIs/models may be used as optional accelerators, not required source-of-truth dependencies. | Design phase and competition constraints. |

## Unknowns

| Area | Unknown |
| --- | --- |
| Official rules | Final 2026 task definitions, timing, and scoring details. |
| Submission API | Endpoint, auth/session mechanism, payload, response semantics, rate limits, and whether correctness feedback is immediate. |
| Metadata completeness | Whether current-year metadata always contains the same fields as the observed sample. |
| Filename stem format | Exact current-year naming pattern, beyond stem matching between `.mp4` and `.json`. |
| Timing | Time limit per clue batch and per question session. |
| Compute | Actual host machine CPU/GPU/RAM/disk available during preparation and final-round operation. |
| Provider choices | Which online APIs/models, if any, the team will use. |

## Out Of Scope For MVP

- Auth and role-based dashboards.
- Submit permission enforcement inside the app.
- Public cloud deployment as the primary runtime target.
- Multi-node distributed runtime.
- Assuming organizer-provided derived artifacts.
- Hard-coded organizer submission payload before official API docs exist.
- Hard dependency on online URLs or external providers for core retrieval correctness.

## Design Implications, Not Final Strategy

- Query Session must store clue batches because the public screen does not preserve earlier clues.
- UI must support fast manual entry from screen-observed clues.
- System 1 must validate raw video / metadata pairing before producing artifacts.
- System 1 must probe media facts including actual FPS.
- System 2 should support current-only and accumulated clue search modes.
- Submission UI should show previous attempts before allowing another submit.
- Online providers can be adapterized later, but local artifacts remain the retrieval source of truth.
