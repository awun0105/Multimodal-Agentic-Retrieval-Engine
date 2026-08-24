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
| MVP-0.5 | App-ready Data Contract defines video plus optional organizer metadata input, required canonical per-video metadata, canonical IDs/refs, bilingual evidence, SQLite/FTS5, separate SigLIP/BEiT3 FAISS boundaries, and validation rules | partial | yes | no | no | changed | ADR 0016 plus metadata/timeline package tests cover the Phase00 contract. Production Phase01 providers, dual indexes, final runtime artifacts, and live full-dataset proof remain pending. |
| MVP-0.6 | System 1 builds app-ready seed artifacts from official videos and optional metadata while generating its own derived evidence | yes | yes | no | no | partial | Phase00 plus the production Phase01 stage/config/checkpoint/package implementations have automated proof. Real TransNet/faster-whisper/Gemini one-video and heterogeneous-batch execution remain pending, as do Phase02 dual indexes and final runtime artifacts. |
| MVP-1 | System 1 builds validated runtime SQLite/FTS5/FAISS artifacts for System 2 | yes | yes | no | no | partial | The debug/mock path builds and validates `app.sqlite`, FTS5, one legacy debug visual index, vector map, and smoke report. The accepted production SigLIP/BEiT3 dual-index path remains unimplemented. |
| MVP-2 | Backend API vertical slice reads System 1 app-ready artifacts and returns keyframe-first payloads | no | no | no | no | planned | backend scaffold only |
| MVP-3 | One React/Vite SPA provides keyframe-first query and inspection workflow | no | no | no | no | planned | frontend scaffold only |
| MVP-4 | FAISS visual retrieval returns ranked keyframe results through FastAPI | no | no | no | no | planned | future System 2 work |
| MVP-5 | SQLite FTS5 text retrieval supports the global `text_documents` contract | no | no | no | no | planned | future System 2 work |
| MVP-6 | Hybrid retrieval fuses vector, text, and metadata/object evidence | no | no | no | no | planned | future System 2 work |
| MVP-7 | Query Session workspace and candidate basket support team use | no | no | no | no | planned | future System 2 work |
| MVP-8 | Submission helper supports editable drafts, history, and a configurable organizer API adapter | no | no | no | no | planned | future System 2 work |
| MVP-9 | Agent v0 uses the same retrieval/evidence APIs and result model | no | no | no | no | planned | future System 2 work |
| SYS1-001 | Vision embedding notebook pipeline produces shard-safe separate SigLIP and BEiT3 embeddings | no | no | no | no | planned | production dual-index feature workflow remains planned |
| SYS1-002 | Gemini OCR and canonical per-video metadata evidence produce shard-safe outputs | partial | yes | no | yes | partial | Canonical per-video metadata generation and validation are covered locally; Gemini OCR and production feature output remain planned. |
| SYS1-003 | Notebook 01 fixed production pipeline produces TransNet shots, search-band keyframes, faster-whisper or optional pinned NeMo ASR, Gemini bilingual captions/scene boundaries/summaries, strict packages, and resumable sync | yes | partial | no | no | partial | The 251-test local suite covers config hashes, batch-scoped Phase00 restore/corruption recovery, writable public-or-private checkpoint preflight, bounded Hugging Face download caches, grouped checkpoint promotion/invalidation, shot partitions, bounded-RAM keyframe selection, ASR/OOM policy, optional NeMo provider configuration/contract, Gemini retry/schema cache, scene voting, package validation, remote-layout contract, and QA sampling. Real-provider/Colab execution remains pending and TransNet artifact provisioning is a preflight blocker. |
| SYS1-004 | Aggregation produces validated SQLite, FTS5, FAISS, vector mapping, and capability artifacts | yes | yes | no | no | partial | Debug/mock merge, build, validate, and smoke path is covered in `system1/tests/test_smoke.py`. |
| SYS1-HR-001 | Notebook 00B/00C streaming raw upload, canonical per-video metadata and decoded timelines, Phase00 ingest/reconciliation, and storage safety | yes | yes | no | yes | implemented locally | Tests cover required timeline generation/retry/validation, resume backfill, compact HF ingest without MP4 download, stale batch/timeline replacement, scoped hash-based Phase00 reconciliation, metadata normalization/provenance, and notebook gates. Live full-dataset HF rehearsal remains pending. |
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
