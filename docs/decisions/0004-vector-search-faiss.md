# 0004 Vector Search: FAISS

Date: 2026-06-12

## Status

Accepted

## Context

The system needs local visual retrieval over keyframes and future multimodal
ranking without relying on cloud vector services.

## Decision

Use FAISS as the MVP vector search index.

## Alternatives Considered

1. SQLite-only approximate vector storage.
2. External vector database.
3. Delaying vector search in favor of text-only retrieval.

## Consequences

Positive:

- Keeps vector retrieval local-first.
- Aligns with keyframe-first search.
- Works well with SQLite mapping tables.

Tradeoffs:

- Requires ingestion/build steps for index generation.
- Vector ID mapping must stay consistent with runtime SQLite.

## Follow-Up

- Define vector-map schema in MVP-1.
- Implement `/api/search/visual` in MVP-3.
