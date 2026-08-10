# Current State

## Status

Repository snapshot refreshed after the canonical per-video metadata contract
sync on 2026-08-10.

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
| Production Phase00 decoded frame timeline from canonical HF raw | partial | Raw upload records inventory probe facts, but canonical HF ingest currently reuses the inventory without staging each video to decode a production timeline. |
| Production Phase01 semantic algorithms | partial | Timeline-aware provider interfaces and explicit debug/fallback artifacts exist. The accepted target is TransNet V2, 20%/50%/80% keyframes, faster-whisper large-v3, Gemini bilingual captions, multimodal context-focus scene grouping, and Gemini bilingual scene summaries. Production providers and their real-video proof remain unfinished; see `docs/architecture/system1-notebook01-production-pipeline.md`. |
| Production Phase02 enrichment and dual visual indexes | partial/debug only | Current code builds a single debug visual embedding/index path. The accepted target is Gemini OCR, configured object detection, and separate SigLIP and BEiT3 FAISS indexes over Notebook 01 keyframes with shared `embeddings_meta`/`vector_map`; it is not implemented yet. |
| System 2 backend | scaffold only | `system2/backend/pyproject.toml` and package placeholders |
| System 2 frontend | scaffold only | minimal `system2/frontend/package.json` and no application source |
| Search adapters, live fusion, Query Sessions, agent runtime, and organizer submission adapter | not implemented | target documentation exists, but System 2 runtime code does not implement it |

## Interpretation Rule

Treat System 1 debug/mock behavior as implemented only where code and tests
provide evidence. Do not describe unfinished production providers or System 2
target architecture as running behavior. Product and architecture decisions
remain normative targets; implementation status belongs here and in
`docs/validation/test-matrix.md`.
