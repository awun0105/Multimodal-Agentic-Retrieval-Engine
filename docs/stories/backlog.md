# Backlog

## Status

Planned backlog derived from onboarding evidence plus accepted canonical product
decisions.

## MVP Story Order

| ID | Title | Type | Priority | Depends On | Notes |
| --- | --- | --- | --- | --- | --- |
| `MVP-0` | Documentation canonicalization and decision records | docs | P0 | none | Update conflicts, add decisions, promote `docs/architecture/system1-ingestion.md` as canonical ingestion source. |
| `MVP-0.5` | App-ready Data Contract | docs | P0 | `MVP-0` | Canonicalize `docs/architecture/data-contracts.md`; define roots, logical refs, IDs, SQLite/FTS5/FAISS mapping, and validation rules before runtime implementation. |
| `MVP-0.6` | Seed Dataset Builder | implementation | P0 | `MVP-0.5` | Create a tiny app-ready fixture plus validation report so backend/UI/retrieval can test against real contract shape. |
| `MVP-1` | Runtime SQLite schema + validation | implementation | P0 | `MVP-0.6` | Create `${AIC_RUNTIME_ROOT}/db/app.sqlite`; define runtime tables and validators; reject absolute paths and unresolved media refs. |
| `MVP-2` | Backend API vertical slice | implementation | P0 | `MVP-1` | FastAPI can read app-ready SQLite/media refs and return keyframe-first result/detail payloads. |
| `MVP-3` | Keyframe-first UI vertical slice | implementation | P0 | `MVP-2` | One React/Vite SPA with result grid, thumbnail lazy loading, detail view, same-video nearby keyframe strip, and copy `video_id/frame_id`. |
| `MVP-4` | Visual retrieval | implementation | P1 | `MVP-1`, `MVP-2` | Load FAISS visual index, map `vector_id` to keyframe via SQLite `vector_map`, implement `/api/search/visual`, show ranked keyframe results. |
| `MVP-5` | SQLite FTS5 text retrieval | implementation | P1 | `MVP-1`, `MVP-2` | Create FTS5 tables for captions/OCR/ASR/metadata/objects; implement `/api/search/text` and modality-specific search. |
| `MVP-6` | Hybrid retrieval | implementation | P1 | `MVP-4`, `MVP-5` | Implement `/api/search/hybrid`; fuse FAISS + FTS5 + metadata/object scores; support search modes and evidence summary. |
| `MVP-7` | Query workspace + candidate basket | implementation | P1 | `MVP-3`, `MVP-6` | Current clue, accumulated clues, selected clues, notes, query history, candidate basket per Query Session, pin/unpin candidate. |
| `MVP-8` | Output helper | implementation | P2 | `MVP-7` | Copy KIS row, Q&A row, TRAKE row, basic validation, configurable CSV helper only if needed. |
| `MVP-9` | Agent v0 | implementation | P2 | `MVP-6`, `MVP-7` | Agent tool adapter; agent calls same retrieval/evidence APIs; agent results appear in same UI; agent logs stored in SQLite. |

## Non-MVP / Deferred

| ID | Title | Reason |
| --- | --- | --- |
| `POST-MVP-1` | MinIO adapter | Optional future adapter only. |
| `POST-MVP-2` | Tantivy or alternate text engine | Revisit only if SQLite FTS5 proves insufficient. |
| `POST-MVP-3` | DuckDB runtime read-only analytics surfaces | Runtime source of truth remains SQLite. |
| `POST-MVP-4` | Advanced rerankers / LVLM verification | Deferred until retrieval baseline is stable. |
| `POST-MVP-5` | Auth and role-based dashboards | Explicitly out of MVP scope. |

## Notes

- Single Web UI does not mean single-user workflow.
- Query Session is the main collaboration boundary for saved state.
- Output helper remains configurable because official 2026 submission rules are incomplete.


## System 1 / System 2 Split Stories

| ID | Title | Type | Priority | Depends On | Notes |
| --- | --- | --- | --- | --- | --- |
| `SYS1-001` | Vision embedding notebook pipeline | implementation | P1 | `MVP-0.5` | Task-specific Jupyter notebook for CLIP/openCLIP embeddings by dataset shard. |
| `SYS1-002` | OCR + metadata notebook pipeline | implementation | P1 | `MVP-0.5` | Notebook for OCR extraction and organizer metadata normalization by shard. |
| `SYS1-003` | Audio transcription notebook pipeline | implementation | P1 | `MVP-0.5` | Notebook for Whisper transcription by shard with time ranges. |
| `SYS1-004` | DuckDB aggregation and artifact merge | implementation | P1 | `SYS1-001`, `SYS1-002`, `SYS1-003` | Merge notebooks outputs into runtime SQLite and FAISS artifacts. |
| `SYS2-001` | FastAPI runtime scaffold | implementation | P1 | `MVP-1` | Base runtime API and SQLite repository layer. |
| `SYS2-002` | React/Vite runtime scaffold | implementation | P1 | `MVP-3` | Base SPA for Query Sessions and keyframe workflow. |
| `SYS2-003` | FAISS runtime adapter | implementation | P1 | `MVP-4` | Runtime visual retrieval adapter. |
| `SYS2-004` | FTS5 runtime adapter | implementation | P1 | `MVP-5` | Runtime text retrieval adapter. |
| `SYS2-005` | Hybrid retrieval + agent integration | implementation | P2 | `MVP-6`, `MVP-9` | Runtime orchestration layer for search fusion and agent results. |
