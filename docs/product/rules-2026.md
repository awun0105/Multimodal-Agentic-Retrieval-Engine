# HCMC AI Challenge 2026 Rules

## Status

Canonical Rules Document. Supersedes the earlier archived rules notes.

See `docs/product/requirements-truth-set.md` for current confirmed requirements, planning assumptions, unknowns, and out-of-scope boundaries.

---

## 1. Verified Competition Scope

- **Multimedia Retrieval**: Tasks are multimedia search and retrieval tasks, not general-purpose chat.
- **Expected Modes**: Visual clue retrieval (TKIS/VKIS), question-answering on keyframe facts (Q&A), and sequence-event search (TRAKE), based on current planning assumptions until official 2026 rules are released.
- **Staged Reveal**: Contest rounds may use progressive clue reveal, where one query exposes subsequent clues over time.
- **Live Operation**: Competitors read questions from a public screen and use their own team system to query.

---

## 2. Structural Unknowns

The rules must support flexible ingestion, validation, and export because these official details are not confirmed:
- Exact dataset contents and filesystems.
- Organizer API endpoint, auth/session mechanism, payload, response semantics, and scoring feedback.
- CSV/ZIP submission file schema constraints.
- Detailed limits for allowed internet/external provider usage during final rounds.


## 3. Historic Assumptions (Prior Years)

While 2026 is unconfirmed, prior years established patterns that guide MVP architecture:
- Group A used TKIS, Q&A, and TRAKE workflows.
- Submission formats used CSV rows with video/frame predictions.
- Ranking rewarded finding the correct answer near the top of up to 100 rows.
- Progressive reveal was used: one query workbook could contain multiple clue batches revealed sequentially over time.

## 4. Current Submission Requirement

Current project requirement expects final-round answers to be submitted through an organizer-provided API. System 2 must allow human-editable answer drafts, explicit submit action, and per-question/session submission history because multiple attempts may be possible and wrong attempts may reduce score. Exact organizer API behavior remains unknown.

## 5. Current Internet Requirement

Current project requirement says internet access is allowed for external APIs/models, URL access, and online metadata/thumbnail access; phones are not allowed. The system should still keep core retrieval local/LAN-first and artifact-backed so network/provider failure does not break correctness.
