# Technical Risks

## Status

Canonical risk register for the MVP docs and early implementation.

| Risk | Impact | Mitigation |
| --- | --- | --- |
| App-ready validation drift | Runtime behavior silently diverges from data contract. | Keep `docs/architecture/data-contracts.md` authoritative; add seed dataset validation before runtime work. |
| Official data format drift | 2026 organizer files may differ from source assumptions. | Keep ingestion configurable; isolate raw import adapters from canonical SQLite/FAISS contract. |
| FAISS index loading time | Large indexes may slow startup or exceed memory. | Use index manifests, lazy loading where possible, and explicit health/status endpoints. |
| Vector mapping mismatch | FAISS result rows may resolve to wrong frames. | Validate every vector row against SQLite `vector_map` and `keyframes`. |
| Cache invalidation errors | Old thumbnails/results may appear after dataset rebuild. | Key cache by `dataset_id`, build id, and index manifest hash; cache is disposable. |
| LAN concurrency on SQLite | Multiple teammates may write sessions/candidates during active search. | Use WAL, short write transactions, session-scoped writes, and avoid long write locks. |
| Text modality sparsity | OCR/ASR/caption/object coverage may be incomplete. | Return evidence availability flags and per-modality score components. |
| Media path portability | Absolute paths break on another machine. | Store logical refs only and resolve through `MediaStorePort`. |
| Agent overreach | Agent may bypass UI/retrieval rules or produce untraceable answers. | Force same APIs as UI, trace tool calls, cap runtime/steps, and require human override. |
| Competition export drift | Final answer format may change. | Keep output helper configurable; avoid hard-coded final submission API assumptions. |
