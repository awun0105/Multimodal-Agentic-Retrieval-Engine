# Backlog

## Status

Planned backlog derived from onboarding evidence plus accepted canonical product
decisions.

## MVP Story Order

| ID | Title | Type | Priority | Depends On | Notes |
| --- | --- | --- | --- | --- | --- |
| `MVP-0` | Documentation canonicalization and decision records | docs | P0 | none | Update conflicts, add decisions, promote `docs/architecture/system1-ingestion.md` as canonical ingestion source. |
| `MVP-0.5` | App-ready Data Contract | docs | P0 | `MVP-0` | Canonicalize `docs/architecture/data-contracts.md`; define roots, logical refs, IDs, SQLite/FTS5/FAISS mapping, and validation rules before runtime implementation. |
| `MVP-0.6` | System 1 mini seed dataset builder | implementation | P0 | `MVP-0.5` | Use a tiny paired subset of raw videos and metadata JSON to validate stem-based `video_id`, generate first app-ready artifacts, and emit validation report before building System 2. |
| `MVP-1` | App-ready artifact builder + runtime SQLite validation | implementation | P0 | `MVP-0.6`, `SYS1-004` | Build validated runtime SQLite/FTS5/FAISS artifacts from System 1 outputs; reject absolute paths and unresolved media refs before System 2 depends on them. |
| `MVP-2` | Backend API vertical slice | implementation | P0 | `MVP-1` | FastAPI reads app-ready artifacts produced by System 1 and returns keyframe-first result/detail payloads. |
| `MVP-3` | Keyframe-first UI vertical slice | implementation | P0 | `MVP-2` | One React/Vite SPA with result grid, thumbnail lazy loading, detail view, same-video nearby keyframe strip, and copy `video_id/frame_id`. |
| `MVP-4` | Visual retrieval | implementation | P1 | `MVP-1`, `MVP-2` | Load FAISS visual index, map `vector_id` to keyframe via SQLite `vector_map`, implement `/api/search/visual`, show ranked keyframe results. |
| `MVP-5` | SQLite FTS5 text retrieval | implementation | P1 | `MVP-1`, `MVP-2` | Create FTS5 tables for captions/OCR/ASR/metadata/objects; implement `/api/search/text` and modality-specific search. |
| `MVP-6` | Hybrid retrieval | implementation | P1 | `MVP-4`, `MVP-5` | Implement `/api/search/hybrid`; fuse FAISS + FTS5 + metadata/object scores; support search modes and evidence summary. |
| `MVP-7` | Query workspace + candidate basket | implementation | P1 | `MVP-3`, `MVP-6` | Current clue, accumulated clues, selected clues, notes, query history, candidate basket per Query Session, pin/unpin candidate. |
| `MVP-8` | Submission helper and organizer API adapter | implementation | P2 | `MVP-7` | Build task-type-specific answer drafts, allow user edit/review, show per-question submission history, and submit through configurable organizer API when official details exist. |
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
- Submission helper remains configurable because official 2026 submission API, payload, and scoring feedback are incomplete; submit responsibility is handled by team process outside the app.


## System 1 / System 2 Split Stories

| ID | Title | Type | Priority | Depends On | Notes |
| --- | --- | --- | --- | --- | --- |
| `SYS1-001` | Vision embedding notebook pipeline | implementation | P1 | `MVP-0.5` | Task-specific pipeline for generated keyframes and CLIP/openCLIP embeddings by dataset shard. |
| `SYS1-002` | OCR + metadata notebook pipeline | implementation | P1 | `MVP-0.5` | Pipeline for OCR extraction plus raw-video/metadata pairing and organizer metadata normalization by shard. |
| `SYS1-003` | Audio transcription notebook pipeline | implementation | P1 | `MVP-0.5` | Notebook for Whisper transcription by shard with time ranges. |
| `SYS1-004` | DuckDB aggregation and app-ready artifact merge | implementation | P1 | `SYS1-001`, `SYS1-002`, `SYS1-003` | Merge System 1 modality outputs into validated runtime SQLite, FTS5, FAISS, and mapping artifacts. |
| `SYS2-001` | FastAPI runtime scaffold | implementation | P1 | `MVP-1` | Base runtime API and SQLite repository layer. |
| `SYS2-002` | React/Vite runtime scaffold | implementation | P1 | `MVP-3` | Base SPA for Query Sessions and keyframe workflow. |
| `SYS2-003` | FAISS runtime adapter | implementation | P1 | `MVP-4` | Runtime visual retrieval adapter. |
| `SYS2-004` | FTS5 runtime adapter | implementation | P1 | `MVP-5` | Runtime text retrieval adapter. |
| `SYS2-005` | Hybrid retrieval + agent integration | implementation | P2 | `MVP-6`, `MVP-9` | Runtime orchestration layer for search fusion and agent results. |
