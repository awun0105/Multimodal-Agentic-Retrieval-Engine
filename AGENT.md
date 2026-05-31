# AGENT.md - Project Source Of Truth

Build a simple web-based multimedia retrieval cockpit for AI Challenge HCMC.

The app is not a chatbot and not a desktop app. It is an LSC/VBS-style browser:

```text
query -> ranked frames -> inspect video/timeline -> choose frame -> export answer
```

## Current Decisions

- Use a **web app**: browser UI + backend API over HTTP.
- Support two runtime modes:
  - `local`: one laptop runs app and opens `localhost`;
  - `LAN`: one host laptop/server runs app, teammates connect by browser.
- Use **precomputed artifacts** for speed. Do not run OCR/ASR/captioning during live search.
- Search over sampled frames/keyframes, not full extracted video frames.
- Keep raw videos for playback and exact inspection.
- Use Google Colab/Kaggle/GPU machines for preprocessing only, not live serving.
- Implement both modes:
  - interactive mode: humans search, filter, inspect video/timeline, and choose;
  - automatic mode: a virtual agent routes the query, calls system tools, chooses,
    and returns final ranked answers.
- Build the interactive cockpit first, then build the automatic agent on top of
  the same APIs/tools.

## Recommended Starting Stack

- Frontend: React + TypeScript + Vite + Tailwind.
- Backend: Python + FastAPI.
- Metadata/app state: SQLite with WAL mode.
- Vector search: FAISS.
- Text/object/OCR search: SQLite FTS5 first.
- Media processing: FFmpeg.
- Packaging/runtime: Docker Compose.
- Evaluation/offline reports: Python scripts, optionally DuckDB later.

Do not introduce PostgreSQL, OpenSearch, Rust, Tauri, Kubernetes, or cloud hosting
unless the simple stack is measured and proven insufficient.

## Coding Standards

Follow `CODING_STANDARDS.md`.

Default principles:

- loose coupling;
- high cohesion;
- readable code over clever code;
- API/service/storage boundaries;
- PEP 8 and Ruff for Python;
- strict TypeScript for frontend;
- tests and validation before commits.

## Data Layout

```text
data/
  raw/
    videos/
    keyframes_official/
    embeddings_official/
    objects/
    metadata/

  processed/
    thumbs/
    keyframes/
    previews/
    dense_frame_cache/   # optional, generated only for inspected clips

  indexes/
    visual.faiss
    visual_map.sqlite
    text.sqlite

  app.sqlite
```

Rules:

- Raw data is immutable.
- `thumbs/`, `keyframes/`, `previews/`, DB, and indexes are generated artifacts.
- Do not extract every frame by default. It is usually much larger than video.
- `dense_frame_cache/` is optional and should be generated on demand around opened
  candidates.

## Core Workflow

1. Ingest official data.
2. Register videos, keyframes, embeddings, objects, and metadata.
3. Generate thumbnails and app keyframes if needed.
4. Build metadata DB, vector index, and text/object indexes.
5. Search query through indexes.
6. Return lightweight result metadata plus thumbnail URLs.
7. User clicks a result to inspect video/timeline/keyframes.
8. User saves candidate and exports validated answer files.

## Product Modes

### Interactive Mode

Human operator controls the workflow:

- search manually;
- choose query type;
- apply filters;
- inspect result grid;
- open video/timeline/keyframes;
- use similar-frame search;
- select frame/time range manually;
- save candidates and export answers.

### Automatic Mode

Virtual agent controls the workflow:

- receive a query;
- classify route: TKIS, Q&A, TRAKE, VKIS-like;
- parse clues and constraints;
- call search, filter, similar-frame, evidence, and timeline tools;
- rerank candidates;
- choose answer/frame sequence;
- return ranked results with evidence and confidence.

Automatic mode must use the same backend APIs as interactive mode. It must log
its steps and should not auto-submit unless official rules allow it.

## Query Types To Support

- TKIS: find video/frame from text description.
- Q&A: find video/frame and produce an answer.
- TRAKE: find ordered event frames in one video.
- VKIS: operator describes a shown visual/video prompt and searches from notes.

## Progressive Reveal

Final queries may appear one sentence at a time. The app should support query
sessions with:

- current clue;
- accumulated clues;
- private notes;
- pinned candidates;
- result comparison across clue batches.

## Performance Rules

- Search should read indexes and DB, not raw videos.
- Result grid should load small thumbnails lazily.
- Raw/preview video loads only when a user opens a candidate.
- Keep DB and indexes on SSD if possible.
- Raw videos can live on external HDD.

## Non-Goals For Now

- No chatbot-first UI.
- No desktop-first architecture.
- No full-frame extraction by default.
- No heavy distributed system.
- No cloud dependency for live competition.
- No auto-submit unless official rules allow it and validation passes.
