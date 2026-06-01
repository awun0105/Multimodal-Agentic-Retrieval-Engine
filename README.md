# Multimodal Agentic Retrieval Engine

Web-based multimedia retrieval cockpit for HCMC AI Challenge.

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
