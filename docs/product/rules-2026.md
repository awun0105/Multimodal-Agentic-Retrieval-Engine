# HCMC AI Challenge 2026 Rules

## Status

Canonical Rules Document. Supersedes the earlier archived rules notes.

---

## 1. Verified Competition Scope

- **Multimedia Retrieval**: Tasks are multimedia search and retrieval tasks, not general-purpose chat.
- **Expected Modes**: Visual clue retrieval (TKIS), question-answering on keyframe facts (Q&A), and sequence-event search (TRAKE).
- **Staged Reveal**: Contest rounds may use progressive clue reveal, where one query exposes subsequent clues over time.

---

## 2. Structural Unknowns

The rules must support flexible ingestion, validation, and export because these official details are not confirmed:
- Exact dataset contents and filesystems.
- API submission format or direct web uploads.
- CSV/ZIP submission file schema constraints.
- Allowed cloud/internet access during final rounds.


## 3. Historic Assumptions (Prior Years)

While 2026 is unconfirmed, prior years established patterns that guide MVP architecture:
- Group A used TKIS, Q&A, and TRAKE workflows.
- Submission formats used CSV rows with video/frame predictions.
- Ranking rewarded finding the correct answer near the top of up to 100 rows.
- Progressive reveal was used: one query workbook could contain multiple clue batches revealed sequentially over time.
