# Architecture Overview

## Current Status

This repository currently contains product and architecture documentation only.
No application runtime code, package manifests, or tests were found during
onboarding.

## Canonical MVP Stack

The accepted MVP stack is:

- Frontend: React/Vite Single Page Application
- Backend: FastAPI
- Runtime DB: SQLite WAL
- Text Search: SQLite FTS5
- Preprocessing/Staging: DuckDB
- Vector Search: FAISS
- Media Storage: LocalFileMediaStore
- Deployment: local machine, local GPU workstation, mini server, or LAN host

Not in MVP:

- auth
- role-based UI
- multiple dashboards
- microservices
- OpenSearch/Elasticsearch
- mandatory MinIO
- mandatory video preview
- hard-coded submission API
- treating 2025 rules as fixed 2026 rules

## Single Web UI + Multi-session Workflow

The system uses one shared web application and one UI codebase. This does not
mean single-user workflow.

Canonical meaning:

- one shared web app for the whole team
- no separate operator/reviewer/admin apps
- no separate UI for agent mode
- no authentication for MVP
- multiple teammates can work from different browsers or machines over LAN
- teammates can work independently or collaboratively through Query Sessions
- each Query Session stores clues, notes, search history, pinned candidates,
  and output-helper state
- optional client nickname or `client_id` may show who added notes/searches,
  but this is not authentication

## High-Level Flow

```text
official/raw dataset
  -> DuckDB preprocessing/staging/validation
  -> app-ready artifacts under `${AIC_DATA_ROOT}` + `${AIC_RUNTIME_ROOT}`
  -> FastAPI retrieval API
  -> React/Vite SPA
  -> Query Sessions / Candidate Basket / Output Helper / Optional Agent Panel
```

## Architectural Style

| Layer | Responsibility | Current Status |
| --- | --- | --- |
| React/Vite SPA | Query workspace, search controls, results grid, detail view, same-video explorer, evidence panel, candidate basket, output helper, optional agent panel | specified, not implemented |
| FastAPI API | HTTP routes, request/response mapping, media URL resolution | specified, not implemented |
| Service Layer | Search workflows, evidence assembly, scoring, export helper logic | specified, not implemented |
| Runtime SQLite | app state, Query Sessions, clues, candidates, agent runs, metadata lookup, vector mapping, captions, OCR, ASR, objects, FTS5 | specified, not implemented |
| DuckDB Warehouse | bulk import, staging, normalization, dataset validation, reports, artifact preparation | specified, not implemented |
| FAISS | visual/vector retrieval | specified, not implemented |
| LocalFileMediaStore | videos, keyframes, thumbnails, generated assets | specified, not implemented |

## Keyframe-first Workflow

The product is keyframe-first:

- Search results primarily show keyframes/thumbnails.
- Detail view opens selected keyframe with metadata and evidence.
- Same Video Explorer loads nearby keyframes.
- Raw video preview/open-at-timestamp is optional and must not auto-load by default.
- Result grids should use lazy loading and virtualization to protect RAM.

## Ingestion Boundaries

`docs/architecture/system1-ingestion.md` is the canonical ingestion planning document.
Archived ingestion inputs are historical only; canonical implementation planning starts from `docs/architecture/system1-ingestion.md`.

Canonical ingestion direction:

- `docs/architecture/data-contracts.md` is the canonical app-ready contract for runtime inputs.
- `docs/architecture/storage-strategy.md` defines repo/data/runtime root separation.

- DuckDB handles bulk import, staging, normalization, and validation.
- SQLite WAL is the runtime source of truth.
- SQLite FTS5 is the MVP text search layer.
- FAISS is the MVP vector search layer.
- Local filesystem is the MVP media store.
- MinIO is an optional future adapter only.

## Output Helper

Submission/export stays configurable and secondary.

Primary support should focus on copy helpers such as:

- `video_id`
- `frame_id`
- `answer`
- `video_id,frame_id`
- `video_id,frame_id,answer`
- `video_id,frame_1,frame_2,...`

CSV/ZIP generation may be added as configurable helpers, but final 2026
submission behavior must not be hard-coded yet.

## Known Tradeoffs

- Simplicity is prioritized over distributed scalability.
- Runtime and preprocessing use different databases on purpose.
- Raw video playback is secondary to keyframe-first retrieval.
- Official 2026 rules are still incomplete, so ingest/export behavior must stay configurable.
