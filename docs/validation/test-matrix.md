# Test Matrix

This Markdown file is the durable behavior-to-proof index. It records
implementation evidence and accepted future scope; it is not derived from a
SQLite Harness database.

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
| MVP-0 | Canonical docs and accepted decisions define the repository contract | no | no | no | no | implemented | `docs/onboarding/doc-conflicts.md`, `docs/decisions/` |
| MVP-0.5 | App-ready Data Contract defines organizer input, canonical IDs and refs, SQLite/FTS5/FAISS boundaries, and validation rules | no | no | no | no | implemented | `docs/architecture/data-contracts.md`, `docs/architecture/system1-ingestion.md` |
| MVP-0.6 | System 1 builds app-ready seed artifacts from paired raw video and metadata | yes | yes | no | no | partial | Debug/mock CLI integration is covered in `system1/tests/test_smoke.py`; production provider depth remains incomplete. |
| MVP-1 | System 1 builds validated runtime SQLite/FTS5/FAISS artifacts for System 2 | yes | yes | no | no | partial | The debug/mock path builds and validates `app.sqlite`, FTS5, visual index, vector map, and smoke report; production-scale/provider proof remains open. |
| MVP-2 | Backend API vertical slice reads System 1 app-ready artifacts and returns keyframe-first payloads | no | no | no | no | planned | backend scaffold only |
| MVP-3 | One React/Vite SPA provides keyframe-first query and inspection workflow | no | no | no | no | planned | frontend scaffold only |
| MVP-4 | FAISS visual retrieval returns ranked keyframe results through FastAPI | no | no | no | no | planned | future System 2 work |
| MVP-5 | SQLite FTS5 text retrieval supports the global `text_documents` contract | no | no | no | no | planned | future System 2 work |
| MVP-6 | Hybrid retrieval fuses vector, text, and metadata/object evidence | no | no | no | no | planned | future System 2 work |
| MVP-7 | Query Session workspace and candidate basket support team use | no | no | no | no | planned | future System 2 work |
| MVP-8 | Submission helper supports editable drafts, history, and a configurable organizer API adapter | no | no | no | no | planned | future System 2 work |
| MVP-9 | Agent v0 uses the same retrieval/evidence APIs and result model | no | no | no | no | planned | future System 2 work |
| SYS1-001 | Vision embedding notebook pipeline produces shard-safe visual embeddings | no | no | no | no | planned | production feature workflow remains planned |
| SYS1-002 | OCR and metadata notebook pipeline produces shard-safe outputs | no | no | no | no | planned | production feature workflow remains planned |
| SYS1-003 | Audio transcription notebook pipeline produces ASR time-range outputs | no | no | no | no | planned | production provider remains unfinished |
| SYS1-004 | Aggregation produces validated SQLite, FTS5, FAISS, vector mapping, and capability artifacts | yes | yes | no | no | partial | Debug/mock merge, build, validate, and smoke path is covered in `system1/tests/test_smoke.py`. |
| SYS1-HR-001 | Notebook 00 Drive shadow, archive standardization, and raw upload hardening | yes | yes | no | yes | implemented | `docs/stories/system1/SYS1-HR-001-production-safe-notebook00/validation.md` |
| SYS2-001 | FastAPI runtime scaffold exposes core retrieval endpoints | no | no | no | no | planned | backend scaffold only |
| SYS2-002 | React/Vite runtime scaffold supports Query Session workflow | no | no | no | no | planned | frontend scaffold only |
| SYS2-003 | FAISS runtime adapter queries vector index and resolves SQLite mappings | no | no | no | no | planned | no runtime adapter implementation |
| SYS2-004 | FTS5 runtime adapter queries SQLite FTS5 tables | no | no | no | no | planned | no runtime adapter implementation |
| SYS2-005 | Hybrid retrieval and agent integration share runtime APIs | no | no | no | no | planned | no runtime orchestration implementation |

## Evidence Rules

- Code and focused tests prove implemented behavior; plans and accepted
  decisions prove intended scope, not completion.
- Debug/mock proof does not establish production provider quality,
  full-dataset scalability, or a running System 2 application.
- Update this matrix with the code, tests, docs, and validation report that
  justify each status change.
