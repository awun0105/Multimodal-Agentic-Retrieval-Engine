# Requirement Truth Set

## Status

Canonical requirement summary for the current planning phase. This file separates confirmed facts, planning assumptions, unknowns, and out-of-scope items before design or implementation strategy starts.

## Confirmed Requirements

| Area | Requirement | Evidence / Source |
| --- | --- | --- |
| Preliminary query types | AIC 2026 preliminary Batch 1 defines Textual KIS, Q&A, and TRAKE workflows. | Official preliminary info in `docs/product/official/aic2026-preliminary-round-batch1/preliminary-round-info.md`. |
| Submission answer unit | Textual KIS and Q&A answers require `video_id` and `frame_id`; Q&A also requires an answer string; TRAKE requires `video_id` plus one `frame_id` per event. | Official preliminary info. |
| Ranking limit | Each query may submit at most 100 answers; scoring averages best `R@k` over `k = {1, 5, 20, 50, 100}`. | Official preliminary info. |
| TRAKE precision | TRAKE first retrieves one video, then aligns one semantic keyframe per event; answer intervals are usually very short. | Official preliminary info. |
| Dataset input | Organizer Batch 1 provides videos plus support artifacts: keyframes, object JSON, CLIP features, map-keyframes/media-info, and YouTube metadata where available. | Official preliminary info and `batch1-downloads.csv`. |
| Official base source material | The official dataset includes videos as the base media source; support artifacts may be imported when validated but must not become hard limits on System 1 generation. | Official preliminary info. |
| Video format | Raw videos are `.mp4`. | Official preliminary info examples and download package names. |
| Metadata pairing | Metadata may be missing for some videos and is optional retrieval evidence, not a condition for including a valid video. | Official preliminary info. |
| Canonical `video_id` | Use the raw video filename stem as canonical `video_id`; do not derive it from `watch_url` or YouTube ID. | Human-confirmed decision. |
| Organizer support artifacts | Organizer-provided keyframes, object detections, and CLIP ViT-B/32 features are support inputs only; System 1 may import them with provenance after mapping validation. | Official preliminary info. |
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
| FPS | Last-year dataset videos were observed at 25 fps; use 25 fps as expected/default while probing actual FPS per current-year video. | Current-year raw media probe. |
| Local-first reliability | Even though internet is allowed, core retrieval should remain local/LAN-first and artifact-backed so network or provider failures do not break correctness. | Design phase and provider selection. |
| Online providers | External APIs/models may be used as optional accelerators, not required source-of-truth dependencies. | Design phase and competition constraints. |

## Unknowns

| Area | Unknown |
| --- | --- |
| Later-round rules | Final-round task timing, progressive reveal behavior, and scoring penalties remain separate from the confirmed preliminary profile. |
| Submission API | Endpoint, auth/session mechanism, payload, response semantics, rate limits, and whether correctness feedback is immediate. |
| Submission file schema | Exact upload/export schema remains unknown beyond the official answer fields. |
| Full 2026 dataset | Batch 2 contents and delivery shape are not yet present in the repo. |
| Filename stem format | Exact future-batch naming pattern, beyond using video filename stem as `video_id`. |
| Timing | Time limit per clue batch and per question session. |
| Compute | Actual host machine CPU/GPU/RAM/disk available during preparation and final-round operation. |
| Provider choices | Which online APIs/models, if any, the team will use. |

## Out Of Scope For MVP

- Auth and role-based dashboards.
- Submit permission enforcement inside the app.
- Public cloud deployment as the primary runtime target.
- Multi-node distributed runtime.
- Assuming organizer-provided support artifacts are complete, correct, or
  sufficient without validation.
- Precomputing query-specific TRAKE event sequences as System 1 canonical
  artifacts.
- Hard-coded organizer submission payload before official API docs exist.
- Hard dependency on online URLs or external providers for core retrieval correctness.

## Design Implications, Not Final Strategy

- Query Session must store clue batches because the public screen does not preserve earlier clues.
- UI must support fast manual entry from screen-observed clues.
- System 1 must validate video identity, support-artifact mapping, and exact
  frame/timestamp resolution before producing app-ready artifacts.
- System 1 must probe media facts including actual FPS.
- System 2 should support current-only and accumulated clue search modes.
- System 2 must treat TRAKE as runtime retrieval, same-video sequence ranking,
  and exact-frame refinement over System 1 reusable artifacts.
- Internal retrieval candidate pools may be larger than 100; exported/submitted
  answer lists must respect the official 100-answer limit.
- Submission UI should show previous attempts before allowing another submit.
- Online providers can be adapterized later, but local artifacts remain the retrieval source of truth.
