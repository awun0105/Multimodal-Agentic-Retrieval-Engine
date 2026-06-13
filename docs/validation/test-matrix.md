# Test Matrix

This file maps current MVP behavior to proof expectations.

Current repository state is documentation-only. The rows below reflect accepted
MVP scope, but no implementation proof exists yet.

## Status Values

| Status | Meaning |
| --- | --- |
| planned | Accepted as intended behavior, not implemented |
| in_progress | Actively being built |
| partial | Partly implemented or weakly proven |
| unknown | Mentioned or expected, but current proof is unclear |
| not_implemented | No implementation evidence was found |
| implemented | Implemented and proof exists |
| changed | Contract changed after earlier implementation |
| retired | No longer part of the product contract |

## Matrix

| Story | Contract | Unit | Integration | E2E | Platform | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MVP-0 | Canonical docs, decisions, and supersession markers match accepted architecture | no | no | no | no | implemented | `docs/onboarding/doc-conflicts.md`, `docs/architecture/overview.md`, `docs/architecture/ingestion.md` (no ADRs required) |
| MVP-0.5 | App-ready Data Contract defines roots, logical refs, IDs, SQLite/FTS5/FAISS boundaries, and validation rules | no | no | no | no | implemented | `docs/architecture/data-contracts.md`, `docs/architecture/system1-ingestion.md`, `docs/stories/backlog.md` |
| MVP-0.6 | Tiny seed dataset fixture and validation report prove the contract is executable | no | no | no | no | planned | planned |
| MVP-1 | Runtime SQLite schema and local file-path validation support the dataset contract | no | no | no | no | planned | planned |
| MVP-2 | Backend API vertical slice reads app-ready SQLite/media refs and returns keyframe-first payloads | no | no | no | no | planned | planned |
| MVP-3 | One React/Vite SPA provides keyframe-first query and inspection workflow | no | no | no | no | planned | planned |
| MVP-4 | FAISS visual retrieval returns ranked keyframe results through FastAPI | no | no | no | no | planned | planned |
| MVP-5 | SQLite FTS5 text retrieval supports captions/OCR/ASR/metadata/object search | no | no | no | no | planned | future MVP |
| MVP-6 | Hybrid retrieval fuses vector, text, and metadata/object evidence | no | no | no | no | planned | future MVP |
| MVP-7 | Query Session workspace and candidate basket support independent/collaborative team use | no | no | no | no | planned | future MVP |
| MVP-8 | Output helper supports configurable copy/export patterns without hard-coded final submission API | no | no | no | no | planned | future MVP |
| MVP-9 | Agent v0 uses the same retrieval/evidence APIs and appears in the same UI/result model | no | no | no | no | planned | future MVP |

| SYS1-001 | Vision embedding notebook pipeline produces shard-safe visual embeddings | no | no | no | no | planned | durable matrix |
| SYS1-002 | OCR and metadata notebook pipeline produces shard-safe outputs | no | no | no | no | planned | durable matrix |
| SYS1-003 | Audio transcription notebook pipeline produces ASR time-range outputs | no | no | no | no | planned | durable matrix |
| SYS1-004 | DuckDB aggregation merges notebook outputs into SQLite and FAISS artifacts | no | no | no | no | planned | durable matrix |
| SYS2-001 | FastAPI runtime scaffold exposes core retrieval endpoints | no | no | no | no | planned | durable matrix |
| SYS2-002 | React/Vite runtime scaffold supports Query Session workflow | no | no | no | no | planned | durable matrix |
| SYS2-003 | FAISS runtime adapter queries vector index and resolves SQLite mappings | no | no | no | no | planned | durable matrix |
| SYS2-004 | FTS5 runtime adapter queries SQLite FTS5 tables | no | no | no | no | planned | durable matrix |
| SYS2-005 | Hybrid retrieval and agent integration share runtime APIs | no | no | no | no | planned | durable matrix |

## Evidence Rules

- MVP-0 through MVP-4 are the concrete near-term validation targets, with MVP-0.5 and MVP-0.6 required before runtime implementation starts.
- MVP-4 and later remain planned until earlier implementation stories exist.
- Unit proof covers pure domain and application rules.
- Integration proof covers backend enforcement, data integrity, provider behavior, jobs, or service contracts.
- E2E proof covers user-visible browser flows.
- Platform proof covers shell, deployment, desktop, or runtime behavior that cannot be proven in lower layers.
