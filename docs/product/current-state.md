# Current State

## Status

Draft until reviewed and confirmed by a human.

## Purpose

Describe the current product state of the Multimodal Agentic Retrieval Engine based only on inspected repository evidence.

## Current Behavior

| Behavior | Status | Evidence |
| --- | --- | --- |
| Local-first multimedia retrieval assistant is specified | confirmed | `SPEC.md`, `README.md` |
| Interactive Mode is specified | confirmed | `SPEC.md`, `UI_IMPLEMENTATION_SPEC.md` |
| Automatic Agent Mode is specified | confirmed | `SPEC.md`, `UI_IMPLEMENTATION_SPEC.md` |
| Configurable submission/export is required | confirmed | `HCMAI-RULES.md`, `SPEC.md` |
| Web UI must support search, inspection, candidate tray, and export preview | partial | `UI_IMPLEMENTATION_SPEC.md`; no frontend code exists |
| Ingestion must produce normalized registry, media assets, and indexes | partial | `docs/references/original-sources/INGESTION.md`; no ingestion code exists |
| SQLite WAL + SQLite FTS5 runtime, DuckDB preprocessing, FAISS vector search, and LocalFileMediaStore are the accepted MVP architecture | confirmed | `docs/decisions/`, `README.md`, `docs/architecture/overview.md` |
| Runtime app exists | not_implemented | No backend/frontend source files found |
| Automated tests exist | not_implemented | No test files or package manifests found |

## Users And Roles

| User/Role | Capability | Notes |
| --- | --- | --- |
| Competition teammate | Search multimedia evidence and inspect candidates | Specified, not implemented |
| Human operator | Save candidates and export answers | Specified, not implemented |
| Automatic agent | Use same retrieval core and tools as UI | Specified, not implemented |

## Inputs And Outputs

| Input | Output | Owner | Notes |
| --- | --- | --- | --- |
| Raw videos | Searchable media registry | Ingestion | Format for 2026 unknown |
| Official keyframes | Thumbnails/keyframes/index mappings | Ingestion | Keyframe-first workflow is preferred |
| OCR/ASR/caption/object metadata | Evidence panel and text search | Ingestion/Search | Optionality depends on available data and compute |
| User query or clue batch | Ranked candidate frames | Retrieval core | Query types include TKIS, Q&A, TRAKE, VKIS |
| Candidate basket | Export rows or copied fields | UI/Export | Final 2026 format unknown |

## Rules And Constraints

- Tier 1 documents win over Tier 2 drafts.
- Final 2026 rules are not confirmed; ingestion, validation, and export must stay configurable.
- Product must not split humans and agents into separate retrieval products.
- Local-first operation and low dependency count are product priorities.
- Search runtime must use precomputed DB/indexes, not raw folder scans or heavy extraction.

## Validation Expectations

| Story/Behavior | Required Proof | Evidence Path |
| --- | --- | --- |
| First backend scaffold | Unit/integration tests for health and config | planned |
| First frontend scaffold | Build proof and basic UI smoke | planned |
| Ingestion MVP | Validation report for app-ready dataset | planned |
| Search MVP | Integration proof against fixture dataset | planned |
| Export MVP | Unit/integration proof for configurable rows | planned |

## Open Questions

- Exact `app.sqlite` schema and FTS5 table layout.
- Exact DuckDB staging table layout and validation outputs.
- What official 2026 rules will constrain cloud/API usage and final submission format?
