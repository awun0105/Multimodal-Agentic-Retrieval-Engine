# System 2: Retrieval Runtime

## Status

Canonical for the live runtime. System 2 is the online query, search, evidence, candidate, and agent application.

## Runtime Flow

```text
human UI or agent query
  -> query/session context
  -> modality adapters
  -> fusion and diversification
  -> optional rerank top-K
  -> evidence builder
  -> candidate/session persistence
  -> UI/API payloads
```

System 2 must not scan raw organizer folders at query time. It reads app-ready artifacts defined in `docs/architecture/data-contracts.md`.

## Core Ports And Adapters

| Component | Role |
| --- | --- |
| `SQLiteRepository` | Reads catalog/evidence and writes query sessions, search runs, candidates, and agent traces. |
| `FaissRetriever` | Queries visual/vector indexes and resolves `vector_id` through SQLite `vector_map`. |
| `Fts5Retriever` | Queries captions, OCR, ASR, objects, and metadata FTS5 tables inside `app.sqlite`. |
| `MediaStorePort` | Resolves logical media refs to served URLs without exposing absolute paths. |
| `LocalFileMediaStore` | MVP implementation backed by `${AIC_DATA_ROOT}/processed/media`. |
| `EvidenceBuilder` | Joins ranked hits to captions, OCR, ASR, objects, metadata, thumbnails, and video refs. |
| `FusionEngine` | Normalizes, weights, diversifies, and reranks adapter outputs. |

## Retrieval Adapters

Minimum adapters:

- Visual adapter: FAISS image/keyframe vectors.
- Caption adapter: generated or imported keyframe/segment captions.
- OCR adapter: text detected in keyframes.
- ASR adapter: spoken transcript segments by video/time range.
- Object adapter: object/concept labels and optional boxes.
- Metadata adapter: title, source/channel, official annotations, tags, duration, fps.

Adapters return normalized hit records with `source`, `score`, `keyframe_id` or resolvable `video_id`/time range, and evidence snippets. API responses must resolve to `keyframe_id`, `video_id`, and `frame_id` before reaching UI.

## Fusion Pipeline

1. Parse query type: TKIS, Q&A, TRAKE, VKIS, or generic hybrid.
2. Run relevant adapters in parallel when available.
3. Normalize scores per adapter to `[0, 1]`.
4. Apply query-type weights from `docs/product/search-fusion.md`.
5. Merge by `keyframe_id` and retain per-modality evidence.
6. Diversify by video when the UI requests it.
7. Rerank top-K candidates with richer evidence when configured.
8. Build UI-ready evidence summaries and validation warnings.

## Write Model

Search reads are mostly read-only. Writes are scoped to Query Sessions:

- `query_sessions`
- `search_runs`
- `candidates`
- `agent_runs`
- `agent_steps`

Multiple LAN users may write to different sessions concurrently. SQLite WAL is the MVP concurrency model; long-running retrieval should not hold write transactions.

## Agent Runtime

The agent is an automation layer on the same APIs and result model as the UI. It may classify query intent, run multi-step retrieval, inspect evidence, save candidates, and propose exports. It must keep traceable tool calls and allow human accept/edit/reject in the same Query Session.
