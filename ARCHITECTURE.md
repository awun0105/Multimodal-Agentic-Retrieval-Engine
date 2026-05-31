# Architecture

## Goal

Build a fast web cockpit for multimedia retrieval:

```text
Browser UI -> FastAPI backend -> SQLite / FAISS / media files
```

The system should run on one laptop or on a LAN host that teammates access from
their browsers.

## Runtime Modes

### Local Mode

```text
Laptop
  - browser
  - backend
  - SQLite DB
  - FAISS/text indexes
  - media files
```

User opens:

```text
http://localhost:8080
```

### LAN Mode

```text
Host machine
  - backend + frontend
  - data + indexes
  - media serving

Team laptops
  - browser only
```

Teammates open:

```text
http://<host-ip>:8080
```

## Main Components

```text
Frontend
  - search page
  - result grid
  - video inspector
  - timeline/keyframe strip
  - candidate tray
  - submission/export panel
  - agent run panel

Backend
  - search API
  - media API
  - query session API
  - candidate API
  - validation/export API
  - agent API

Storage
  - filesystem for videos, thumbnails, keyframes, previews
  - SQLite for metadata and app state
  - FAISS for visual/vector search
  - SQLite FTS5 for text/object/OCR search
```

## Product Modes

### Interactive Mode

The user drives the system through the Web UI:

```text
manual query/filter/search
  -> result grid
  -> video/timeline inspection
  -> candidate selection
  -> validation/export
```

### Automatic Mode

A virtual agent drives the same backend tools:

```text
query
  -> route/classify
  -> plan tool calls
  -> search/filter/inspect evidence
  -> rerank
  -> choose answer or frame sequence
  -> return ranked results
```

The agent must not bypass the retrieval APIs, media/evidence APIs, candidate
model, or validator. It is an orchestration layer over the same system the human
uses.

## Search Flow

```text
user query
  -> parse query
  -> search vector/text/object indexes
  -> fuse and diversify results
  -> return frame candidates
  -> UI loads thumbnails
  -> user opens video/timeline
  -> user saves final candidate
```

The search API returns metadata and URLs, not image/video bytes inside JSON.

Example result:

```json
{
  "video_id": "L21_V001",
  "frame_id": 1234,
  "timestamp": 49.36,
  "thumb_url": "/media/thumbs/L21_V001/001234.webp",
  "keyframe_url": "/media/keyframes/L21_V001/001234.jpg",
  "score": 0.82,
  "evidence": ["object: Lantern", "caption: city festival"]
}
```

## Media Serving

- Result grid uses small thumbnails.
- Inspector uses keyframes and preview/raw video.
- Video should support HTTP range requests for seeking.
- Dense frame extraction is generated only on demand around selected candidates.

## Data Placement

Best case:

```text
SSD:
  app.sqlite
  indexes/
  processed/thumbs/

External HDD:
  raw/videos/
  processed/keyframes/
  processed/previews/
```

If SSD space is limited, prioritize:

1. SQLite DB
2. FAISS/text indexes
3. thumbnails
4. keyframes
5. raw videos

## Implementation Order

1. Data manifest and media registry.
2. Thumbnail/keyframe browser.
3. Text/object search.
4. FAISS visual search.
5. Hybrid result grid.
6. Video inspector and timeline.
7. Candidate tray and export validator.
8. Query-specific helpers for Q&A, TRAKE, VKIS.
9. Agent/automation later.
