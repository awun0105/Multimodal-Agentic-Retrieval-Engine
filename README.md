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
- LAN: one host machine runs app, runtime artifacts, and media/data; teammates open the shared Web UI by host IP address from their browsers.
- One shared SPA supports multiple teammates through Query Sessions.

## Data

Raw videos are kept as video files. The app searches precomputed indexes and
shows thumbnails/keyframes. Full dense frames are not extracted by default.
