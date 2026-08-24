# Current State

## Status

Repository snapshot refreshed during Notebook 01 production implementation on
2026-08-16.

## Implemented And Observed

| Area | State | Evidence |
| --- | --- | --- |
| System 1 Python package and `system1` CLI | implemented | `system1/pyproject.toml`, `system1/src/system1/cli.py` |
| Debug/mock System 1 release path through ingest, batching, processing, merge, index, SQLite build, validation, and smoke reporting | implemented for the debug/mock profile | `system1/README.md`, `system1/tests/test_smoke.py` |
| Repository Harness Core 0.1.7 workflow | installed | `.harness-core/manifest.json`, `AGENTS.md`, `docs/WORKFLOW.md` |

## Partial Or Not Implemented

| Area | State | Evidence |
| --- | --- | --- |
| Canonical per-video metadata in Notebook 00B/00C | implemented and locally validated | Both raw upload package paths generate schema 1.0 JSON for every video, retain organizer source reference/checksum without a duplicate HF tree, retry `ffprobe`, project the same facts into inventory, and propagate provenance through canonical HF ingest. Notebook gates and automated tests cover the contract; a live full-dataset `canonical_raw_v009` upload has not yet been run. |
| Production Phase00 decoded frame timeline from canonical HF raw | implemented and locally validated | Notebook 00B/00C create each decoded timeline while the video is already in bounded upload scratch. The raw inventory and progress record its path/status/row count; required resume backfills older missing timelines; canonical HF ingest downloads and validates only the compact Parquet, not the MP4. Automated tests cover the workflow, while a live full-dataset `canonical_raw_v009` rehearsal remains pending. |
| Production Phase01 semantic algorithms | implemented, externally blocked from live proof | The public `process-batch` path and thin Notebook 01 implement batch-scoped checksum-resumable Phase00 restore, deterministic resolved config, writable public-or-private per-video/per-stage checkpoints with grouped output commits, dependency invalidation, TransNet V2 subprocess inference, one-pass bounded-RAM search-band keyframes, faster-whisper large-v3 OOM recovery, optional pinned NeMo/Parakeet Vietnamese ASR with FFmpeg silence segmentation, Gemini Interactions structured captions/boundaries/summaries with stage-local request cache/retry/concurrency controls, bounded scratch-scoped Hugging Face download caches, strict package validation, sync verification, remote layout verification, and QA/worker reports. The complete local suite passes 251 tests. A live run still requires the one-time verified TransNet artifact/checksum, credentials, and real-provider acceptance proof; see `docs/plans/active/notebook01-production-pipeline.md`. |
| Production Phase02 enrichment and dual visual indexes | partial/debug only | Current code builds a single debug visual embedding/index path. The accepted target is Gemini OCR, configured object detection, and separate SigLIP and BEiT3 FAISS indexes over Notebook 01 keyframes with shared `embeddings_meta`/`vector_map`; it is not implemented yet. |
| System 2 backend | scaffold only | `system2/backend/pyproject.toml` and package placeholders |
| System 2 frontend | scaffold only | minimal `system2/frontend/package.json` and no application source |
| Search adapters, live fusion, Query Sessions, agent runtime, and organizer submission adapter | not implemented | target documentation exists, but System 2 runtime code does not implement it |

## Interpretation Rule

Treat System 1 debug/mock behavior as implemented only where code and tests
provide evidence. Do not describe the implemented Phase01 adapters as
production-validated until real-provider acceptance passes, and do not describe
System 2 target architecture as running behavior. Product and architecture
decisions remain normative targets; implementation status belongs here and in
`docs/validation/test-matrix.md`.
