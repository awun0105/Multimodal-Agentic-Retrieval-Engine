# Implementation Plan

Branch: `implementation/web-retrieval-system`

Goal: build a simple web-based multimedia retrieval system with a FastAPI backend
and React/Vite frontend. The first usable version should search precomputed
metadata/artifacts, show frame results, inspect video/keyframes, save candidates,
and expose a foundation for automatic agent mode.

## Phase 0: Plan And Project Skeleton

- Add this implementation plan.
- Add project config files.
- Add backend and frontend folders.
- Add Docker Compose for local/LAN usage.

## Phase 1: Backend Foundation

- FastAPI app with health endpoint.
- SQLite database bootstrap.
- Config from environment variables.
- Static media serving for thumbnails/keyframes/videos.
- Minimal seed/demo data support.

## Phase 2: Search And Candidate APIs

- Search endpoint over SQLite demo metadata.
- Candidate save/list APIs.
- Query session and clue APIs.
- Validation/export stubs.

## Phase 3: Frontend Foundation

- React/Vite app shell.
- Search page and result grid.
- Candidate inspector panel.
- Candidate tray.
- API client.

## Phase 4: Interactive Workflow

- Search from UI.
- Open result details.
- Save candidate.
- Show evidence and media URLs.
- Progressive clue session UI.

## Phase 5: Automatic Mode Foundation

- Agent run API.
- Route query type.
- Call search internally.
- Return ranked results with a simple trace.
- UI panel for agent run output.

## Phase 6: Validation And Hardening

- Backend tests.
- Frontend build check.
- Docker Compose smoke check.
- Update README with run instructions.

## Commit Policy

Commit and push after each small completed phase. Do not merge this branch.

