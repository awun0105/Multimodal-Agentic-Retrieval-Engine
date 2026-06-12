# Technical Spec

## Product

A web-based LSC/VBS-style retrieval cockpit for AI Challenge HCMC.

Primary workflow:

```text
search -> frame grid -> video/timeline inspect -> save candidate -> export
```

Required modes:

- Interactive mode: human searches, filters, inspects, chooses, and exports.
- Automatic mode: virtual agent receives query, routes, uses tools, chooses, and
  returns ranked answer rows with evidence.

## Tech Stack

Use this stack first:

| Area | Choice |
|---|---|
| Frontend | React + TypeScript + Vite |
| Styling | Tailwind CSS |
| Backend API | Python + FastAPI |
| App DB | SQLite with WAL |
| Vector search | FAISS |
| Text/object search | SQLite FTS5 |
| Media | Filesystem + FFmpeg |
| Packaging | Docker Compose |
| Tests | pytest for backend, basic frontend checks later |

Optional later only if needed:

- DuckDB for analytics/evaluation reports.
- PostgreSQL if SQLite write concurrency becomes a problem.
- Tantivy/OpenSearch if FTS5 is not enough.
- GPU workers for offline preprocessing.

## API Surface

Minimum APIs:

```text
GET  /health
GET  /datasets
POST /search
POST /similar-frame
GET  /videos/{video_id}
GET  /videos/{video_id}/frames
GET  /media/thumbs/{video_id}/{frame_id}
GET  /media/keyframes/{video_id}/{frame_id}
GET  /media/video/{video_id}
POST /sessions
POST /sessions/{id}/clues
POST /candidates
POST /export
POST /validate
POST /agent/run
GET  /agent/runs/{run_id}
```

## Database Tables

Start simple:

```text
videos
  video_id, path, fps, duration, width, height

frames
  id, video_id, frame_id, timestamp, thumb_path, keyframe_path

objects
  frame_id, video_id, name, score, box_json

evidence
  id, video_id, frame_id, type, text, score, source

query_sessions
  id, query_type, title, created_at

query_clues
  id, session_id, text, order_index

candidates
  id, session_id, video_id, frame_id, timestamp, answer, rank, note

agent_runs
  id, session_id, status, query, route, confidence, created_at

agent_steps
  id, run_id, step_index, tool, input_json, output_json, latency_ms
```

Add tables only when the workflow needs them.

## Query Types

- TKIS: output likely `video_id,frame_id`.
- Q&A: output likely `video_id,frame_id,answer`.
- TRAKE: output likely `video_id,frame_id_1,...,frame_id_n`.
- VKIS: operator enters structured notes from visual prompt.

Exact output rules stay configurable until official rules are confirmed.

## Performance Targets

| Action | Target |
|---|---:|
| First search results | under 2 seconds |
| Thumbnail grid visible | under 2 seconds |
| Open candidate inspector | under 1-3 seconds |
| Similar frame search | under 1 second if index is warm |
| Export/validate | under 1 second |

## Implementation Priorities

P0:

- data layout and config;
- video/keyframe registry;
- thumbnail generation;
- SQLite DB;
- simple text/object search;
- result grid;
- video inspector;
- candidate tray;
- export validator.

P1:

- FAISS visual search;
- hybrid search fusion;
- progressive query sessions;
- similar-frame search;
- official embedding import;
- object JSON normalization.

P2:

- Q&A helper;
- TRAKE timeline helper;
- VKIS structured note form;
- OCR/ASR/caption import or generation;
- bounded agent automation using the same search/media/evidence APIs.
