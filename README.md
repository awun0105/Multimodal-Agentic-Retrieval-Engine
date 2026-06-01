# Multimodal Agentic Retrieval Engine

Web-based multimedia retrieval system for HCMC AI Challenge.

The system is designed for LSC/VBS-style workflows:

```text
search query -> ranked frame results -> inspect video/timeline -> choose frame -> export answer
```

## Architecture

- Frontend: React + TypeScript + Vite.
- Backend: Python + FastAPI.
- DB: SQLite.
- Vector search: FAISS.
- Text/object search: SQLite FTS5.
- Media: filesystem + FFmpeg.
- Runtime: Docker Compose.

## Runtime Modes

- Local: run everything on one machine and open `localhost`.
- LAN: one host machine runs app/data, teammates open the Web UI by IP address.

## Data

Raw videos are kept as video files. The app searches precomputed indexes and
shows thumbnails/keyframes. Full dense frames are not extracted by default.

The current implementation supports a JSON manifest importer:

```bash
uv run aic-ingest path/to/manifest.json
```

Minimal manifest shape:

```json
{
  "videos": [
    {
      "video_id": "L01_V001",
      "path": "raw/videos/L01_V001.mp4",
      "fps": 25,
      "duration": 120,
      "width": 1920,
      "height": 1080
    }
  ],
  "frames": [
    {
      "video_id": "L01_V001",
      "frame_id": 100,
      "timestamp": 4.0,
      "thumb_path": "processed/thumbs/L01_V001/100.jpg",
      "keyframe_path": "processed/keyframes/L01_V001/100.jpg",
      "caption": "A person crossing a busy street",
      "objects": [{"name": "Person", "score": 0.91, "box": [0.1, 0.2, 0.5, 0.8]}]
    }
  ]
}
```

Paths are relative to `AIC_DATA_ROOT`, which defaults to `data/`.

## Current Features

- text search over frame captions and object metadata;
- optional object filters;
- frame result grid with thumbnails/keyframe inspector;
- full frame list for the selected video;
- similar-frame exploration from the selected frame;
- query sessions for progressive clue batches;
- automatic mode foundation with route and tool trace;
- candidate save/edit/rank workflow;
- export preview and validation stub;
- raw video link when the local video file exists.

## Development

Backend:

```bash
uv run uvicorn aic_retrieval.main:app --app-dir backend --reload
```

Frontend:

```bash
npm install --prefix frontend
npm run dev --prefix frontend
```

If port `8000` is occupied, start the backend on another port and point Vite at
it:

```bash
uv run uvicorn aic_retrieval.main:app --app-dir backend --port 8001
AIC_BACKEND_URL=http://localhost:8001 npm run dev --prefix frontend
```

Open:

```text
http://localhost:5173
```

Docker Compose:

```bash
docker compose up --build
```

Open:

```text
http://localhost:8080
```

Validation:

```bash
uv run ruff check backend tests
uv run pytest
npm run build --prefix frontend
```
