# System 2: Retrieval Runtime

## Status

Canonical for the live runtime. System 2 is the online query, search, evidence, candidate, submission, and agent application.

## Runtime Flow

```text
human UI or agent query
  -> query/session context
  -> modality adapters
  -> fusion and diversification
  -> optional rerank top-K
  -> evidence builder
  -> candidate/session persistence
  -> answer draft and explicit human submission
  -> UI/API payloads
```

System 2 must not scan raw organizer folders or raw metadata JSON at query time. It reads only app-ready artifacts defined in `docs/architecture/data-contracts.md`.

System 2 assumes `video_id` is the organizer filename stem chosen by System 1
during video identity and artifact-mapping validation.

## Core Ports And Adapters

| Component | Role |
| --- | --- |
| `SQLiteRepository` | Reads catalog/evidence and writes query sessions, search runs, candidates, and agent traces. |
| `FaissRetriever` | Queries visual/vector indexes and resolves `vector_id` through SQLite `vector_map`. |
| `Fts5Retriever` | Queries the FTS5-backed text search contract built from `text_documents` inside `app.sqlite`. |
| `MediaStorePort` | Resolves logical media refs to served URLs without exposing absolute paths. |
| `LocalFileMediaStore` | MVP implementation backed by `${AIC_DATA_ROOT}/processed/media`. |
| `EvidenceBuilder` | Joins ranked hits to caption evidence, OCR, ASR, objects, metadata-derived text, thumbnails, and video refs. |
| `FusionEngine` | Normalizes, weights, diversifies, and reranks adapter outputs. |
| `SubmissionPort` | Sends reviewed answers to organizer API when official endpoint/auth/payload are known. |
| `SubmissionHistoryStore` | Persists drafts, attempts, response snapshots, status, actor, and timestamps per Query Session. |

## Retrieval Adapters

Minimum adapters:

- Visual adapter: FAISS image/keyframe vectors.
- Caption adapter: project-generated bilingual shot captions and scene
  summaries.
- OCR adapter: text detected in keyframes.
- ASR adapter: spoken transcript segments by video/time range.
- Object adapter: object/concept labels and optional boxes.
- Metadata adapter: title, source/channel, normalized organizer metadata, tags,
  duration, fps when metadata exists. Missing metadata is a missing evidence
  source, not a search failure.

Adapters return normalized hit records with `source`, `score`, `keyframe_id` or resolvable `video_id`/time range, and evidence snippets. API responses must resolve to `keyframe_id`, `video_id`, and `frame_id` before reaching UI.

## Fusion Pipeline

1. Parse query type: TKIS, Q&A, TRAKE, or optional later-round/internal VKIS or
   generic hybrid.
2. Run relevant adapters in parallel when available.
3. Normalize scores per adapter to `[0, 1]`.
4. Apply query-type weights from `docs/product/search-fusion.md`.
5. Merge by `keyframe_id` and retain per-modality evidence.
6. Diversify by video when the UI requests it.
7. Rerank top-K candidates with richer evidence when configured.
8. Build UI-ready evidence summaries and validation warnings.

## Temporal Search

Temporal search is a System 2 query operator and reasoning layer, not a
separate System 1 model or a dedicated release artifact.

Canonical temporal flow:

```text
user query
  -> temporal query parsing
  -> event candidate retrieval
  -> same-video sequence construction
  -> temporal constraint solving when required by query semantics
  -> sequence reranking
  -> exact-frame refinement
  -> evidence clip / same-video context builder
```

Recommended runtime modules:

- `TemporalQueryParser`: converts a user query into event clauses plus temporal
  constraints such as `before`, `after`, `within`, `same_scene`, `same_shot`,
  or ordered `sequence`.
- `TemporalCandidateRetriever`: reuses the normal adapters and runtime
  contracts to retrieve candidates for each event from visual, caption, OCR,
  ASR, object, and metadata evidence.
- `TemporalSequenceRanker`: joins candidates by `video_id` and timeline, applies
  temporal constraints, and reranks valid sequences.
- `EvidenceBuilder`: returns sequence evidence, not only a single frame, for
  example start/end timestamps, neighboring keyframes, transcript overlap, and
  same-shot or same-scene context.

The baseline implementation may be rule-based. Learned reranking is optional
later work. System 2 should prefer explicit temporal constraints and
inspectable evidence over opaque sequence scoring that is difficult to debug in
competition operations. TRAKE answer rows rank complete sequences, not
independent frame hits.

## Write Model

Search reads are mostly read-only. Writes are scoped to Query Sessions:

- `query_sessions`
- `search_runs`
- `candidates`
- `submission_drafts`
- `submissions`
- `agent_runs`
- `agent_steps`

Multiple LAN users may write to different sessions concurrently. SQLite WAL is the MVP concurrency model; long-running retrieval should not hold write transactions.

## Agent Runtime

Organizer final-round submission is expected to happen through organizer API, but endpoint, auth/session mechanism, payload, response semantics, and rate limits are unknown. System 2 must keep submission provider details configurable and must not hard-code a final payload before official rules exist. The MVP app does not implement submit roles; teammate submit responsibility is handled by team process outside the app.

The agent is an automation layer on the same APIs and result model as the UI. It may classify query intent, run multi-step retrieval, inspect evidence, save candidates, and prepare submission drafts. It must keep traceable tool calls and allow human accept/edit/reject in the same Query Session. It must not submit to organizer API without explicit human confirmation.
