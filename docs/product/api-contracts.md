# API Contracts

## Status

Canonical API contract specification for System 2. Derived from `SPEC.md`.

## API Principles

- Keep APIs simple and local-first.
- Use REST for most actions.
- Use WebSocket or SSE only when progress streaming is truly needed.
- Return lightweight result objects first, then lazy-load heavy detail/evidence.
- Agent and UI should call the same APIs where practical.

## Dataset APIs

```http
GET  /api/datasets
GET  /api/datasets/{dataset_id}
POST /api/datasets/select
GET  /api/datasets/{dataset_id}/health
```

## Query Session APIs

```http
POST   /api/query-sessions
GET    /api/query-sessions
GET    /api/query-sessions/{session_id}
PUT    /api/query-sessions/{session_id}
DELETE /api/query-sessions/{session_id}

POST   /api/query-sessions/{session_id}/clues
PUT    /api/query-sessions/{session_id}/clues/{clue_id}
DELETE /api/query-sessions/{session_id}/clues/{clue_id}

POST   /api/query-sessions/{session_id}/notes
GET    /api/query-sessions/{session_id}/history
```

## Search APIs

```http
POST /api/search
POST /api/search/visual
POST /api/search/caption
POST /api/search/ocr
POST /api/search/asr
POST /api/search/object
POST /api/search/metadata
POST /api/search/similar-frame
POST /api/search/within-video
```

### Generic Search Request

```json
{
  "dataset_id": "aic2026",
  "session_id": "optional-session-id",
  "query": "person in white protective suit inside cave",
  "query_type": "tkis",
  "search_mode": "hybrid",
  "strategy": "visual_heavy",
  "top_k": 100,
  "group_by_video": false,
  "top_per_video": 3,
  "filters": {
    "video_names": [],
    "objects": [],
    "has_ocr": null,
    "has_asr": null
  },
  "options": {
    "rerank": false,
    "include_evidence_summary": true,
    "diversify": true
  }
}
```

### Search Response

```json
{
  "search_run_id": "sr_123",
  "latency_ms": 842,
  "results": [
    {
      "rank": 1,
      "video_name": "L01_V028",
      "frame_id": 25300,
      "keyframe_id": "kf_abc",
      "thumbnail_url": "/api/keyframes/kf_abc/thumbnail",
      "score": 0.842,
      "scores": {
        "visual": 0.88,
        "caption": 0.72,
        "ocr": 0.0,
        "asr": 0.51,
        "object": 0.69
      },
      "evidence_summary": {
        "caption": "A person wearing protective clothing in a cave.",
        "ocr": "",
        "asr": "French interview about cave...",
        "objects": ["person", "helmet"]
      }
    }
  ]
}
```

## Keyframe and Media APIs

```http
GET /api/keyframes/{keyframe_id}
GET /api/keyframes/{keyframe_id}/thumbnail
GET /api/keyframes/{keyframe_id}/image
GET /api/videos/{video_name}/keyframes
GET /api/videos/{video_name}/nearby-keyframes?frame_id=25300&window=20
GET /api/videos/{video_name}/metadata
GET /api/videos/{video_name}/preview?frame_id=25300
```

Video preview is optional and must not auto-load by default.

## Evidence APIs

```http
GET  /api/evidence/by-frame?video_name=L01_V028&frame_id=25300
POST /api/evidence/batch
```

### Evidence Response

```json
{
  "video_name": "L01_V028",
  "frame_id": 25300,
  "caption": "...",
  "ocr": ["..."],
  "asr_segments": [
    {
      "start_time_sec": 1000.0,
      "end_time_sec": 1015.0,
      "text": "..."
    }
  ],
  "objects": [
    {"label": "person", "score": 0.91}
  ],
  "metadata": {
    "title": "...",
    "description": "..."
  }
}
```

## Candidate APIs

```http
POST   /api/query-sessions/{session_id}/candidates
GET    /api/query-sessions/{session_id}/candidates
PUT    /api/query-sessions/{session_id}/candidates/{candidate_id}
DELETE /api/query-sessions/{session_id}/candidates/{candidate_id}
```

### Candidate Request

```json
{
  "video_name": "L01_V028",
  "frame_id": 25300,
  "answer": null,
  "trake_frames": null,
  "notes": "Maybe correct because OCR/title matches clue.",
  "label": "maybe"
}
```

## Output Helper APIs

```http
POST /api/output/make-row
POST /api/output/validate-row
POST /api/output/export-csv
POST /api/output/export-zip
```

These APIs are optional helpers and must not assume the final 2026 submission interface.

## Agent APIs

```http
POST /api/agent/runs
GET  /api/agent/runs/{agent_run_id}
POST /api/agent/runs/{agent_run_id}/cancel
```

### Agent Run Request

```json
{
  "dataset_id": "aic2026",
  "session_id": "optional-session-id",
  "query": "Find the video where a person cuts a cake and answer how many pieces are visible.",
  "query_type": "qa",
  "constraints": {
    "max_steps": 6,
    "max_runtime_sec": 45,
    "top_k": 100
  }
}
```
