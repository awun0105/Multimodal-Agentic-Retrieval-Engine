# Acceptance Criteria Summary

## Status

Canonical Acceptance Criteria. Supersedes the earlier source specification acceptance notes.

## MVP Search Workbench

The system is acceptable for MVP when:

1. A developer can register a local dataset using System 1 notebooks/DuckDB aggregator.
2. The runtime system (System 2) can load metadata and a visual FAISS index.
3. The Web UI can search and display ranked keyframes.
4. A user can click a result and see the larger keyframe, metadata, and evidence summary.
5. A user can browse nearby keyframes from the same video.
6. A user can save candidates to a basket inside a Query Session.
7. A user can copy `video_id`, `frame_id`, and `video_id,frame_id`.
8. The app runs locally on one machine (SQLite WAL + FastAPI + React/Vite).
9. The app can be hosted on one machine and exposed over LAN for shared browser access.
10. The host machine is the single runtime holder of SQLite, FAISS, and media/data artifacts during LAN use.
11. The UI avoids loading all images at once and does not exceed RAM constraints during normal use.

## Competition Practice Ready

The system is acceptable for competition practice when:

1. It supports query sessions with clues and notes.
2. It supports hybrid retrieval over visual, caption, OCR, and ASR if data is available.
3. It supports the Q&A answer helper.
4. It supports the TRAKE frame sequence helper.
5. It supports optional output row generation.
6. It has basic agent mode calling the same retrieval APIs.
7. It can run a mock contest session without crashing or leaking memory.
