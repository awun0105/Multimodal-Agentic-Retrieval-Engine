# System 2: Retrieval Engine (Runtime App)

## Status

Canonical System 2 Architecture. Derived from `SPEC.md`.

## Architectural Position

System 2 is the **live, online query, search, and validation application**. It runs during active competition use and is exposed locally or over LAN.

```text
user / agent query
  -> FastAPI Search Controller
  -> Retriever Adapters (FAISS, SQLite FTS5)
  -> Hybrid Scoring & Fusion
  -> Evidences Panel & Detailed Inspector
  -> Query Sessions / Candidate Basket
```

---

## 1. Clean Architecture Layers

System 2 must strictly separate concern layers to maintain debuggability under pressure.

### API Layer
FastAPI routes that handle HTTP requests and response mapping.
- Receives queries, type filters, and current sessions.
- Exposes stream endpoints for video files.
- Return response payloads in snake_case JSON models.

### Service Layer
Contains workflow and domain business logic.
- **Retriever Orchestrator**: Orchestrates queries to visual and text layers.
- **Scoring & Fusion Engine**: Combines FAISS cosine similarity scores and FTS5 BM25 text scores using configurable weights.
- **Export Validator**: Validates basket outputs against rule constraints.

### Repository / Storage Layer
Handles persistent IO.
- SQLite WAL repository classes.
- MediaStore adapters (`LocalFileMediaStore` MVP) for URI translation.
- FAISS client wrappers.

### UI Layer
The React Single Page Application loaded by browser clients.

---

## 2. Runtime Database Optimization

To support sub-second query times with multiple LAN users, the SQLite database must run in WAL mode with normal synchronization.

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;
```

Search routines should be read-only lookups. Write operations (saving candidate cards, notes, query history) are small and scoped to independent Query Sessions.

---

## 3. Search and Retrieval Pattern

The search engine uses the Adapter and Strategy patterns to keep retrieval modular:
1. **Retriever Adapters**:
   - `FaissRetriever`: Queries visual vector space.
   - `Fts5Retriever`: Queries FTS5 virtual tables.
   - `ObjectFilter`: Filters metadata/objects counts from SQLite tables.
2. **Search Strategies**:
   - `TkisStrategy` (Textual KIS): Combines FTS5 text indexes with visual similarities.
   - `QaStrategy` (Visual Q&A): Weights FTS5 object filtering heavily before ranking visual matches.
   - `TrakeStrategy` (Temporal Relationship): Scans consecutive keyframes chronologically to identify sequence matches.
   - `VkisStrategy` (Video KIS): Groups frame similarities by video constraints.
