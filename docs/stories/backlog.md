# Backlog

## Status

Planned backlog derived from onboarding evidence plus accepted canonical product
decisions.

## MVP Story Order

| ID | Title | Type | Priority | Depends On | Notes |
| --- | --- | --- | --- | --- | --- |
| `MVP-0` | Documentation canonicalization and decision records | docs | P0 | none | Update conflicts, add decisions, promote `docs/architecture/system1-ingestion.md` as canonical ingestion source. |
| `MVP-1` | Dataset + SQLite runtime schema | implementation | P0 | `MVP-0` | Create `app.sqlite`; define `videos`, `keyframes`, `captions`, `ocr_texts`, `asr_segments`, `objects`, `vector_map`, `query_sessions`, `query_clues`, `search_runs`, `candidates`, `agent_runs`; validate local file paths. |
| `MVP-2` | Keyframe-first UI | implementation | P0 | `MVP-1` | One React/Vite SPA with result grid, thumbnail lazy loading, detail view, same-video nearby keyframe strip, and copy `video_id/frame_id`. |
| `MVP-3` | Visual retrieval | implementation | P1 | `MVP-1` | Load FAISS visual index, map `vector_id` to keyframe via SQLite, implement `/api/search/visual`, show ranked keyframe results. |
| `MVP-4` | SQLite FTS5 text retrieval | implementation | P1 | `MVP-1` | Create FTS5 tables for captions/OCR/ASR/metadata/objects; implement `/api/search/text` and modality-specific search. |
| `MVP-5` | Hybrid retrieval | implementation | P1 | `MVP-3`, `MVP-4` | Implement `/api/search/hybrid`; fuse FAISS + FTS5 + metadata/object scores; support search modes and evidence summary. |
| `MVP-6` | Query workspace + candidate basket | implementation | P1 | `MVP-2`, `MVP-5` | Current clue, accumulated clues, selected clues, notes, query history, candidate basket per Query Session, pin/unpin candidate. |
| `MVP-7` | Output helper | implementation | P2 | `MVP-6` | Copy KIS row, Q&A row, TRAKE row, basic validation, configurable CSV helper only if needed. |
| `MVP-8` | Agent v0 | implementation | P2 | `MVP-5`, `MVP-6` | Agent tool adapter; agent calls same retrieval/evidence APIs; agent results appear in same UI; agent logs stored in SQLite. |

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
| `SYS1-001` | Vision embedding notebook pipeline | implementation | P1 | `MVP-1` | Task-specific Jupyter notebook for CLIP/openCLIP embeddings by dataset shard. |
| `SYS1-002` | OCR + metadata notebook pipeline | implementation | P1 | `MVP-1` | Notebook for OCR extraction and organizer metadata normalization by shard. |
| `SYS1-003` | Audio transcription notebook pipeline | implementation | P1 | `MVP-1` | Notebook for Whisper transcription by shard with time ranges. |
| `SYS1-004` | DuckDB aggregation and artifact merge | implementation | P1 | `SYS1-001`, `SYS1-002`, `SYS1-003` | Merge notebooks outputs into runtime SQLite and FAISS artifacts. |
| `SYS2-001` | FastAPI runtime scaffold | implementation | P1 | `MVP-1` | Base runtime API and SQLite repository layer. |
| `SYS2-002` | React/Vite runtime scaffold | implementation | P1 | `MVP-2` | Base SPA for Query Sessions and keyframe workflow. |
| `SYS2-003` | FAISS runtime adapter | implementation | P1 | `MVP-3` | Runtime visual retrieval adapter. |
| `SYS2-004` | FTS5 runtime adapter | implementation | P1 | `MVP-4` | Runtime text retrieval adapter. |
| `SYS2-005` | Hybrid retrieval + agent integration | implementation | P2 | `MVP-5`, `MVP-8` | Runtime orchestration layer for search fusion and agent results. |
