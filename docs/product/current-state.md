# Current State

## Status

Repository snapshot refreshed during the Harness Core 0.1.7 migration on
2026-08-04.

## Implemented And Observed

| Area | State | Evidence |
| --- | --- | --- |
| System 1 Python package and `system1` CLI | implemented | `system1/pyproject.toml`, `system1/src/system1/cli.py` |
| Debug/mock System 1 release path through ingest, batching, processing, merge, index, SQLite build, validation, and smoke reporting | implemented for the debug/mock profile | `system1/README.md`, `system1/tests/test_smoke.py` |
| Repository Harness Core 0.1.7 workflow | installed | `.harness-core/manifest.json`, `AGENTS.md`, `docs/WORKFLOW.md` |

## Partial Or Not Implemented

| Area | State | Evidence |
| --- | --- | --- |
| Production phase01 semantic algorithms | partial | Timeline-aware provider interfaces and fallback artifacts exist; production TransNet V2, ASR, VLM captioning, and scene summarization providers remain unfinished. |
| System 2 backend | scaffold only | `system2/backend/pyproject.toml` and package placeholders |
| System 2 frontend | scaffold only | minimal `system2/frontend/package.json` and no application source |
| Search adapters, live fusion, Query Sessions, agent runtime, and organizer submission adapter | not implemented | target documentation exists, but System 2 runtime code does not implement it |

## Interpretation Rule

Treat System 1 debug/mock behavior as implemented only where code and tests
provide evidence. Do not describe unfinished production providers or System 2
target architecture as running behavior. Product and architecture decisions
remain normative targets; implementation status belongs here and in
`docs/validation/test-matrix.md`.
