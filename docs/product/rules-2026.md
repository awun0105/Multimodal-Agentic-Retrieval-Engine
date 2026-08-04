# HCMC AI Challenge 2026 Rules

## Status

Canonical Rules Document. Supersedes the earlier archived rules notes.

See `docs/product/requirements-truth-set.md` for current confirmed requirements, planning assumptions, unknowns, and out-of-scope boundaries.

---

## 1. Verified Preliminary Scope

- **Multimedia Retrieval**: Tasks are multimedia search and retrieval tasks, not general-purpose chat.
- **Textual KIS**: Given a complete natural-language event description, return `video_id` and a `frame_id` inside the answer range.
- **Q&A**: Given a natural-language event description and question, return `video_id`, a `frame_id` inside the answer range, and a Vietnamese or English answer.
- **TRAKE**: Retrieve one video and align one semantic keyframe per event in the query sequence. Semantic keyframes are content moments and are not codec I-frames.
- **Ranking**: Each preliminary query accepts at most 100 answers. Scoring uses the best answer within `R@1`, `R@5`, `R@20`, `R@50`, and `R@100`.
- **Live Operation**: Competitors read questions from a public screen and use their own team system to query.

---

## 2. Official Preliminary Data

Batch 1 includes:

- Videos.
- Keyframes named under per-video folders, with frame positions available
  through metadata/map files.
- Object JSON files per keyframe from Faster R-CNN pretrained on OpenImages V4.
- CLIP features from `clip-ViT-B-32` stored in `.npy` order matching keyframe order.
- YouTube metadata JSON when available.
- Additional download artifacts such as map-keyframes and media-info.

The official dataset includes videos as the base media source. Keyframes,
objects, CLIP features, and metadata are support artifacts for solution
building. System 1 may import them as evidence after validating mapping and
provenance, and may also generate better or additional app-ready artifacts from
the videos when that improves retrieval.

Metadata is useful evidence when present. Missing metadata must not exclude a
video from the app-ready dataset if the video identity and frame mapping are
valid.

## 3. Structural Unknowns

The rules must support flexible ingestion, validation, and export because these official details are not confirmed:

- Organizer API endpoint, auth/session mechanism, payload, response semantics, and scoring feedback.
- CSV/ZIP submission file schema constraints beyond the official answer fields.
- Detailed limits for allowed internet/external provider usage during final rounds.
- Batch 2 contents, naming, and delivery timing.

## 4. Later-Round Assumptions

Prior years and user-provided final-round context still guide later-round
architecture, but they must not override the confirmed preliminary profile:

- Staged reveal may be used, where one query exposes subsequent clues over time.
- Visual KIS or other task variants may appear later.
- Multiple submissions may be possible; wrong attempts may reduce score.

## 5. Current Submission Requirement

Current project requirement expects final-round answers to be submitted through
an organizer-provided API. For the preliminary round, System 2 must at minimum
produce validated top-100 answer exports for TKIS, Q&A, and TRAKE. Direct API
submission remains a thin adapter until official organizer transport behavior
is known.

System 2 must allow human-editable answer drafts, explicit submit/export
action, and per-question/session submission history because multiple attempts
may be possible in later rounds and review is still useful during preliminary
practice.

## 6. Current Internet Requirement

Current project requirement says internet access is allowed for external APIs/models, URL access, and online metadata/thumbnail access; phones are not allowed. The system should still keep core retrieval local/LAN-first and artifact-backed so network/provider failure does not break correctness.
