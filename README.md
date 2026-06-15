# Multimodal Agentic Retrieval Engine

Web-based multimedia retrieval cockpit for HCMC AI Challenge.

The repository is organized around three top-level surfaces:

- `system1/`: data factory / preprocessing / dataset release builder
- `system2/`: runtime retrieval app, including backend and frontend
- `docs/`: canonical documentation

The system is designed for LSC/VBS-style workflows:

```text
search query -> ranked frame results -> inspect video/timeline -> choose frame -> export answer
```

## Architecture

- System 1: preprocessing, release building, validation, and dataset packaging.
- System 2 backend: Python + FastAPI.
- System 2 frontend: React + TypeScript + Vite.
- Runtime DB: SQLite.
- Vector search: FAISS.
- Text search: SQLite FTS5.
- Media: filesystem + FFmpeg.
- Runtime: Docker Compose.

## Runtime Modes

- Local: run everything on one machine and open `localhost`.
- LAN: one host machine runs app, runtime artifacts, and media/data; teammates open the shared Web UI by host IP address from their browsers.
- One shared SPA supports multiple teammates through Query Sessions.

## Data

System 1 consumes raw videos + metadata and produces app-ready artifacts. System 2 reads the release package, searches precomputed indexes, and shows thumbnails/keyframes. Full dense frames are not extracted by default.
