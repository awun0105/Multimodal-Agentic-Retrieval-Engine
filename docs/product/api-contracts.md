# Product API Contracts

## Status

Canonical product-facing API shape. Names here must match `docs/architecture/data-contracts.md`.

Requirements context: `docs/product/requirements-truth-set.md`.

## Naming Rules

- Use `video_id` for API and DB payloads.
- Use `frame_id` as integer video frame number.
- Use `keyframe_id = "{video_id}:{frame_id}"` as API/DB glue id.
- Use probed per-video `fps` to compute `timestamp_sec`; last-year evidence suggests 25 fps as a planning/default expected value, not a universal hard-coded runtime divisor.
- Treat `legacy video-name field` only as legacy wording in old source material, not as canonical payload field.
- URL path params containing `keyframe_id` must be URL-safe encoded by clients because the value contains `:`.

## Health And Dataset

```http
GET /api/health
GET /api/datasets/current
GET /api/datasets/current/health
```

Dataset health payload:

```json
{
  "dataset_id": "aic2026",
  "status": "ready",
  "build_id": "2026-06-13T00-00-00Z",
  "counts": {
    "videos": 0,
    "keyframes": 0,
    "captions": 0,
    "ocr_texts": 0,
    "asr_segments": 0,
    "objects": 0,
    "vectors": 0
  },
  "indexes": [
    {"name": "visual", "kind": "faiss", "status": "ready", "vectors": 0},
    {"name": "caption_fts", "kind": "fts5", "status": "ready", "rows": 0}
  ],
  "validation": {
    "status": "pass",
    "report_ref": "reports/aic2026-validation.json",
    "warnings": []
  }
}
```

## Media And Catalog

```http
GET /api/media/thumbnail/{keyframe_id}
GET /api/media/keyframe/{keyframe_id}
GET /api/media/video/{video_id}
GET /api/videos/{video_id}
GET /api/keyframes/{keyframe_id}
GET /api/videos/{video_id}/keyframes?around_frame_id=25300&window=20
GET /api/keyframes/{keyframe_id}/evidence
```

Keyframe payload:

```json
{
  "keyframe_id": "L01_V028:25300",
  "video_id": "L01_V028",
  "frame_id": 25300,
  "timestamp_sec": 843.33,
  "thumbnail_url": "/api/media/thumbnail/L01_V028%3A25300",
  "keyframe_url": "/api/media/keyframe/L01_V028%3A25300",
  "video_url": "/api/media/video/L01_V028",
  "evidence_summary": {
    "caption": "...",
    "ocr": ["..."],
    "asr": ["..."],
    "objects": ["person", "car"],
    "metadata": {"source": "..."}
  }
}
```

## Query Sessions

```http
POST /api/sessions
GET /api/sessions
GET /api/sessions/{session_id}
PATCH /api/sessions/{session_id}
POST /api/sessions/{session_id}/clues
GET /api/sessions/{session_id}/search-runs
```

Session payload:

```json
{
  "session_id": "qs_001",
  "name": "Textual KIS round 1",
  "query_type": "tkis",
  "client_label": "teammate-a",
  "active_clues": ["red bus", "rainy street"],
  "clue_mode": "accumulated",
  "notes": "manual notes",
  "created_at": "2026-06-13T00:00:00Z",
  "updated_at": "2026-06-13T00:00:00Z"
}
```

`client_label` is lightweight teammate attribution only. It is not authentication and does not imply role or permission enforcement.

## Search

```http
POST /api/search
```

Request:

```json
{
  "session_id": "qs_001",
  "query_type": "tkis",
  "query_text": "red bus on rainy street",
  "clue_mode": "current_only",
  "filters": {
    "video_id": null,
    "modalities": ["visual", "caption", "ocr", "asr", "object", "metadata"],
    "group_by_video": true
  },
  "top_k": 100,
  "rerank_top_k": 50
}
```

Response:

```json
{
  "search_run_id": "sr_001",
  "session_id": "qs_001",
  "query_type": "tkis",
  "results": [
    {
      "keyframe_id": "L01_V028:25300",
      "video_id": "L01_V028",
      "frame_id": 25300,
      "timestamp_sec": 843.33,
      "score": 0.87,
      "score_components": {
        "visual": 0.91,
        "caption": 0.72,
        "ocr": 0.0,
        "asr": 0.44,
        "object": 0.66,
        "metadata": 0.15
      },
      "evidence": [
        {"type": "caption", "text": "...", "score": 0.72, "source": "caption_fts"},
        {"type": "object", "text": "bus", "score": 0.66, "source": "object_fts"}
      ],
      "warnings": []
    }
  ]
}
```

## Candidates

```http
POST /api/sessions/{session_id}/candidates
GET /api/sessions/{session_id}/candidates
PATCH /api/sessions/{session_id}/candidates/{candidate_id}
DELETE /api/sessions/{session_id}/candidates/{candidate_id}
```

Candidate payload:

```json
{
  "candidate_id": "cand_001",
  "session_id": "qs_001",
  "keyframe_id": "L01_V028:25300",
  "video_id": "L01_V028",
  "frame_id": 25300,
  "answer_text": null,
  "trake_sequence": [],
  "score_snapshot": 0.87,
  "evidence_snapshot": [],
  "validation_warnings": [],
  "created_by": "teammate-a"
}
```

## Submission Drafts And History

Organizer submission API details are unknown. Internal API shape must therefore model drafts and history without hard-coding final organizer payloads.

```http
POST /api/sessions/{session_id}/submission-drafts
GET /api/sessions/{session_id}/submission-drafts
PATCH /api/sessions/{session_id}/submission-drafts/{draft_id}
POST /api/sessions/{session_id}/submissions
GET /api/sessions/{session_id}/submissions
GET /api/submissions/{submission_id}
```

Submission draft payload:

```json
{
  "draft_id": "draft_001",
  "session_id": "qs_001",
  "query_type": "tkis",
  "candidate_ids": ["cand_001"],
  "answer_payload": {
    "video_id": "L21_0001",
    "frame_id": 25300,
    "answer_text": null,
    "trake_sequence": []
  },
  "validation_warnings": ["official submission payload format unknown"],
  "edited_by": "teammate-a"
}
```

Submission history payload:

```json
{
  "submission_id": "sub_001",
  "session_id": "qs_001",
  "draft_id": "draft_001",
  "query_type": "tkis",
  "status": "submitted",
  "attempt_number": 1,
  "submitted_payload_snapshot": {
    "video_id": "L21_0001",
    "frame_id": 25300
  },
  "organizer_response_status": "unknown",
  "organizer_response_snapshot": null,
  "submitted_by": "teammate-a",
  "submitted_at": "2026-06-14T00:00:00Z"
}
```

Submission rules:

- Submit is per active question/session.
- Multiple submissions may be possible, but wrong attempts may reduce score.
- UI must show submission history before new submit attempts.
- Organizer feedback may be immediate correctness, accepted-only, or unknown until official API behavior is known.
- The app does not model submit roles in MVP; teammate submit responsibility is handled by team process outside the app.

## Agent Runs

```http
POST /api/sessions/{session_id}/agent-runs
GET /api/sessions/{session_id}/agent-runs
GET /api/agent-runs/{agent_run_id}
POST /api/agent-runs/{agent_run_id}/cancel
```

Agent run payload:

```json
{
  "agent_run_id": "ar_001",
  "session_id": "qs_001",
  "status": "running",
  "query_type": "tkis",
  "max_steps": 8,
  "max_runtime_sec": 60,
  "tool_calls": [
    {"step": 1, "tool": "search", "arguments": {"query_text": "red bus"}, "result_count": 50}
  ],
  "selected_candidates": ["cand_001"],
  "summary": "candidate rationale",
  "human_override": "pending"
}
```
