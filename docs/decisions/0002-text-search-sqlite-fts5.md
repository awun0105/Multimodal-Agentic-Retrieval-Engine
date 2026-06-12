# 0002 Text Search: SQLite FTS5

Date: 2026-06-12

## Status

Accepted

## Context

The MVP needs local text retrieval over captions, OCR, ASR, metadata, and object
labels without introducing heavy search infrastructure.

## Decision

Use SQLite FTS5 as the MVP text-search layer.

## Alternatives Considered

1. Tantivy.
2. OpenSearch / Elasticsearch.
3. JSON-only BM25 sparse search.

## Consequences

Positive:

- Keeps text retrieval inside the runtime SQLite stack.
- Minimizes deployment and operational complexity.
- Aligns with local/LAN MVP constraints.

Tradeoffs:

- Future scale or ranking complexity may justify Tantivy or other engines.
- Historical BM25/JSON artifacts remain reference material only.

## Follow-Up

- Define FTS5 tables in MVP-1.
- Use SQLite FTS5 as the baseline for MVP-4 text retrieval.
