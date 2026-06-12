# Data Contracts Specification

## Status

Canonical data contract for System 1 ingestion outputs and System 2 runtime inputs.
Derived from `DATA_READY.md`, `docs/references/original-sources/INGESTION.md`, and accepted decisions.

## System Boundary

- **System 1** produces the data artifacts below through offline notebooks and aggregation.
- **System 2** consumes these artifacts at runtime through SQLite WAL, SQLite FTS5, FAISS, and local media files.
- DuckDB is preprocessing/staging only; it is not the MVP runtime source of truth.

## Global Identity Contract

| Field | Format | Example | Required | Notes |
| --- | --- | --- | --- | --- |
| `video_id` | Organizer/system video ID | `L01_V028` | yes | Stable video key across all tables. |
| `frame_id` | Integer frame number | `25300` | yes for frame-level rows | Use official frame ID if available. |
| `keyframe_id` | `{video_id}_{frame_id}` | `L01_V028_25300` | yes for keyframes | Glue key for media, evidence, search, and candidates. |
| `doc_id` | `{type}_{key}` | `caption_L01_V028_25300` | yes for text docs | Used for FTS/evidence lookup. |
| `vector_id` / `row_id` | integer vector row | `982331` | yes for FAISS mapping | Must align exactly with FAISS row index. |

## App-ready Directory Contract

```text
data/
  media/
    videos/
    keyframes/
    thumbnails/

  db/
    app.sqlite              # Runtime DB: metadata + app state + FTS5

  preprocessing/
    staging.duckdb           # System 1 staging only

  indexes/
    visual.faiss
    visual_mapping.parquet

  config/
    paths.yaml
    retrieval_weights.yaml
    export_rules.yaml

  logs/
    search_runs.jsonl

  exports/
```

## Runtime SQLite Pragmas

System 2 must initialize SQLite runtime DB with:

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;
```

Optional machine-dependent pragmas:

```sql
PRAGMA temp_store=MEMORY;
PRAGMA mmap_size=<machine dependent>;
```

## Runtime SQLite Tables

### `videos`

```sql
CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    uri TEXT NOT NULL,
    duration_sec REAL,
    fps REAL,
    width INTEGER,
    height INTEGER,
    num_frames INTEGER,
    has_audio INTEGER,
    source TEXT,
    metadata_json TEXT
);
```

Required for:

- mapping video IDs;
- grouping results by video;
- computing timestamp/frame relationships;
- checking missing files;
- opening raw video only on demand.

### `keyframes`

```sql
CREATE TABLE IF NOT EXISTS keyframes (
    keyframe_id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    frame_id INTEGER NOT NULL,
    timestamp_sec REAL,
    keyframe_uri TEXT NOT NULL,
    thumbnail_uri TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    shot_id TEXT,
    source TEXT NOT NULL,
    FOREIGN KEY(video_id) REFERENCES videos(video_id),
    UNIQUE(video_id, frame_id)
);
```

Required for:

- result grid;
- selected frame detail;
- same-video strip;
- copy helpers;
- TRAKE sequence editing;
- Q&A grounding.

### `objects`

```sql
CREATE TABLE IF NOT EXISTS objects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    frame_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    score REAL,
    bbox_json TEXT,
    source TEXT,
    aliases_json TEXT,
    FOREIGN KEY(video_id, frame_id) REFERENCES keyframes(video_id, frame_id)
);
```

Object records must keep:

- label;
- confidence score;
- bounding box when available;
- Vietnamese/English aliases when available.

### `ocr_texts`

```sql
CREATE TABLE IF NOT EXISTS ocr_texts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    frame_id INTEGER NOT NULL,
    raw_text TEXT NOT NULL,
    normalized_text TEXT,
    no_accent_text TEXT,
    lowercase_text TEXT,
    bbox_json TEXT,
    confidence REAL,
    source TEXT,
    FOREIGN KEY(video_id, frame_id) REFERENCES keyframes(video_id, frame_id)
);
```

OCR should preserve raw and normalized variants because competition queries may use exact signs, names, locations, or no-accent Vietnamese text.

### `captions`

```sql
CREATE TABLE IF NOT EXISTS captions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    frame_id INTEGER,
    shot_id TEXT,
    caption_vi TEXT,
    caption_en TEXT,
    model TEXT,
    confidence REAL,
    source TEXT,
    FOREIGN KEY(video_id) REFERENCES videos(video_id)
);
```

Captioning rules:

- Prefer bilingual captions when feasible.
- English captions are useful for CLIP-like model alignment.
- Vietnamese captions are useful for local query intent and manual inspection.

### `asr_segments`

```sql
CREATE TABLE IF NOT EXISTS asr_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    start_sec REAL NOT NULL,
    end_sec REAL NOT NULL,
    start_frame INTEGER,
    end_frame INTEGER,
    text TEXT NOT NULL,
    normalized_text TEXT,
    no_accent_text TEXT,
    english_translation TEXT,
    language TEXT,
    confidence REAL,
    source TEXT,
    FOREIGN KEY(video_id) REFERENCES videos(video_id)
);
```

ASR contract:

- ASR is time-range evidence, not fake per-frame text.
- Word-level timestamps are optional.
- Runtime lookup for selected keyframe should use exact containment or a nearby time window.

Example lookup:

```sql
SELECT *
FROM asr_segments
WHERE video_id = ?
  AND start_frame <= ?
  AND end_frame >= ?;
```

Fallback lookup may use a ±30 second window.

### `evidence_documents`

```sql
CREATE TABLE IF NOT EXISTS evidence_documents (
    doc_id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    frame_id INTEGER,
    shot_id TEXT,
    doc_type TEXT NOT NULL,
    text TEXT NOT NULL,
    fields_json TEXT,
    source TEXT,
    FOREIGN KEY(video_id) REFERENCES videos(video_id)
);
```

Use this table for merged search documents:

- keyframe document;
- shot document;
- video document;
- ASR segment document.

### `vector_map`

```sql
CREATE TABLE IF NOT EXISTS vector_map (
    row_id INTEGER PRIMARY KEY,
    vector_id INTEGER,
    keyframe_id TEXT NOT NULL,
    video_id TEXT NOT NULL,
    frame_id INTEGER NOT NULL,
    model TEXT NOT NULL,
    dim INTEGER NOT NULL,
    source TEXT NOT NULL,
    FOREIGN KEY(keyframe_id) REFERENCES keyframes(keyframe_id)
);
```

FAISS rule:

- Row `N` in `visual.faiss` must map to `vector_map.row_id = N`.
- `visual_mapping.parquet` is allowed as a rebuild/debug artifact, but SQLite `vector_map` is the runtime mapping source.

### `timeline_keyframes`

```sql
CREATE TABLE IF NOT EXISTS timeline_keyframes (
    video_id TEXT NOT NULL,
    frame_id INTEGER NOT NULL,
    timestamp_sec REAL,
    ordinal INTEGER NOT NULL,
    keyframe_id TEXT NOT NULL,
    PRIMARY KEY(video_id, frame_id),
    FOREIGN KEY(keyframe_id) REFERENCES keyframes(keyframe_id)
);
```

Required for:

- same-video strip;
- nearby frame navigation;
- TRAKE chronological verification;
- progressive clue checking.

### `query_sessions`

```sql
CREATE TABLE IF NOT EXISTS query_sessions (
    session_id TEXT PRIMARY KEY,
    query_type TEXT,
    title TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
);
```

### `query_clues`

```sql
CREATE TABLE IF NOT EXISTS query_clues (
    clue_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    clue_index INTEGER NOT NULL,
    clue_text TEXT NOT NULL,
    created_by TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES query_sessions(session_id)
);
```

### `search_runs`

```sql
CREATE TABLE IF NOT EXISTS search_runs (
    run_id TEXT PRIMARY KEY,
    session_id TEXT,
    query_text TEXT NOT NULL,
    search_mode TEXT NOT NULL,
    top_k INTEGER,
    latency_ms INTEGER,
    weights_json TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES query_sessions(session_id)
);
```

### `candidates`

```sql
CREATE TABLE IF NOT EXISTS candidates (
    candidate_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    video_id TEXT NOT NULL,
    frame_id INTEGER NOT NULL,
    answer TEXT,
    note TEXT,
    rank INTEGER,
    score REAL,
    pinned INTEGER DEFAULT 0,
    created_by TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES query_sessions(session_id),
    FOREIGN KEY(video_id, frame_id) REFERENCES keyframes(video_id, frame_id)
);
```

### `agent_runs`

```sql
CREATE TABLE IF NOT EXISTS agent_runs (
    run_id TEXT PRIMARY KEY,
    session_id TEXT,
    status TEXT NOT NULL,
    input_json TEXT,
    tool_calls_json TEXT,
    output_json TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    FOREIGN KEY(session_id) REFERENCES query_sessions(session_id)
);
```

## SQLite FTS5 Contract

Use FTS5 for MVP text search.

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS evidence_fts USING fts5(
    doc_id UNINDEXED,
    video_id UNINDEXED,
    frame_id UNINDEXED,
    doc_type,
    text,
    tokenize='unicode61 remove_diacritics 2'
);
```

FTS source inputs:

- captions;
- OCR;
- ASR;
- metadata;
- object labels/aliases;
- scene/action tags when available.

## Optional / Deferred Data Tables

These are not required for MVP but have accepted future use.

| Data | Priority | Notes |
| --- | --- | --- |
| `audio_events` | P2 | applause, music, siren, crowd, vehicle sounds. |
| `shots` | P1 | group keyframes into shot/segment ranges. |
| `scene_tags` | P2 | indoor/outdoor, place, environment. |
| `visual_attributes` | P2 | colors, clothing, dominant visual cues. |
| `persons` | P2 | person bbox, clothing, pose; avoid identity focus unless rules allow. |
| `object_tracks` | P2/P3 | tracking across keyframes, useful for TRAKE. |
| `action_tags` | P2/P3 | running, handshake, cooking, scoring goal. |
| `entities` | P1/P2 | locations, organizations, people, topics from OCR/ASR/captions. |
| `query_expansions` | P1 | Vietnamese/English synonyms and domain phrases. |
| `candidate_diversification` | P1/P2 | cluster/frame grouping to avoid duplicate top results. |
| `similarity_graph` | P2 | precomputed similar keyframes if FAISS runtime is insufficient. |
| `trake_event_candidates` | P2 | query-time or light precompute candidate sequences. |
| `qa_answer_candidates` | P2 | suggested normalized answers. |
| `inventory_health` | P0 | validation report rows for missing files and artifact completeness. |

## Notebook Artifact Formats

### Visual Embedding Shard

```text
outputs/{shard_id}/visual/{video_id}_dense.npy
outputs/{shard_id}/visual/{video_id}_embedding_map.jsonl
```

Each map row:

```json
{"row_offset": 0, "video_id": "L01_V028", "frame_id": 25300, "keyframe_id": "L01_V028_25300", "model": "clip-vit-l14", "dim": 768}
```

### OCR Shard

```text
outputs/{shard_id}/ocr/{video_id}_ocr.jsonl
```

Each row:

```json
{"video_id":"L01_V028","frame_id":25300,"text":"HỘI NGHỊ","normalized_text":"hoi nghi","bbox":[100,50,700,120],"confidence":0.91}
```

### ASR Shard

```text
outputs/{shard_id}/asr/{video_id}_transcript.jsonl
```

Each row:

```json
{"video_id":"L01_V028","start_sec":1008.0,"end_sec":1020.5,"start_frame":25200,"end_frame":25512,"text":"...","language":"vi","confidence":0.84}
```

### Caption Shard

```text
outputs/{shard_id}/captions/{video_id}_captions.jsonl
```

Each row:

```json
{"video_id":"L01_V028","frame_id":25300,"caption_vi":"...","caption_en":"...","model":"qwen2.5-vl","confidence":0.82}
```

### Object Shard

```text
outputs/{shard_id}/objects/{video_id}_objects.jsonl
```

Each row:

```json
{"video_id":"L01_V028","frame_id":25300,"label":"person","score":0.97,"bbox":[120,80,400,600]}
```


## 5. Preprocessing & Supporting Schema Details

### Thumbnail Specifications
- **Format**: WebP (`.webp`) format is mandatory to minimize HDD load and browser memory.
- **Resolution Tiers**:
  - `thumb_160`: Width 160px (proportional height). Used for virtualized result grids and same-video strips.
  - `thumb_320`: Width 320px (proportional height). Used for Candidate Basket cards and hover previews.
- **Preview Image**: Raw keyframe full-size scaled to max 1280px width (JPEG/PNG) used in detailed inspector before video player loading.

### Query Expansion Dictionary
Stored as JSON in the config folder (`config/query_expansion.json`) and parsed at startup:
```json
{
  "xe máy": ["motorbike", "motorcycle", "scooter"],
  "phát biểu": ["speech", "speaker", "podium", "microphone", "presentation"],
  "múa lân": ["lion dance", "dragon dance", "festival"],
  "đám đông": ["crowd", "audience", "people gathering"]
}
```

### Candidate Diversification Contract
To prevent the top 100 results from being dominated by visually identical adjacent frames from the same video:
```json
{
  "video_id": "L01_V028",
  "cluster_id": "cluster_881",
  "representative_frame_id": 25300,
  "member_frame_ids": [25280, 25300, 25320]
}
```
At runtime, the retrieval engine should apply video-level or shot-level clustering rules (max $N$ keyframes per video/shot in the top $K$ results).

### Preprocessing Inventory Health Data
System 1 must produce a dataset health manifest (`data/inventory_health.json`) after merging:
```json
{
  "video_id": "L01_V028",
  "video_exists": true,
  "keyframe_count": 320,
  "embedding_count": 320,
  "ocr_count": 318,
  "caption_count": 320,
  "asr_segments": 25,
  "missing_files": []
}
```

### Search Run Log Format
Runtime queries must append details to `logs/search_runs.jsonl`:
```json
{
  "run_id": "search_20260609_001",
  "query": "người áo trắng hang động",
  "search_mode": "hybrid",
  "top_k": 100,
  "latency_ms": 842,
  "weights": {
    "visual": 0.4,
    "caption": 0.3,
    "ocr": 0.1,
    "asr": 0.1,
    "object": 0.1
  },
  "top_results": [
    {"video_id": "L01_V028", "frame_id": 25300, "score": 0.88}
  ]
}
```

## Storage Priority

### P0 Mandatory

- `media/videos`
- `media/keyframes`
- `media/thumbnails`
- `app.sqlite` with runtime metadata, app state, and FTS5
- `visual.faiss`
- `vector_map` / `visual_mapping.parquet`
- `timeline_keyframes`
- `query_sessions`
- `candidates`

### P1 Should Have Early

- OCR;
- ASR/transcripts;
- normalized text fields;
- object/concept tags;
- captions;
- evidence documents;
- search logs;
- copy/export config;
- query expansion dictionary.

### P2/P3 Deferred

- dense LVLM captions for all frames;
- text embedding indexes;
- scene/action/person tracking;
- TRAKE event candidates;
- Q&A answer candidates;
- similarity graph;
- audio event tags.

## Runtime Loading Rules

Load into RAM:

- FAISS index if it fits;
- small config;
- recent search results;
- small LRU thumbnail cache;
- hot metadata cache.

Do not load into RAM:

- raw videos;
- full keyframes;
- all thumbnails;
- all captions;
- all OCR;
- all ASR;
- raw embedding `.npy` files.

If FAISS is too large:

- use FAISS mmap / IVF / PQ;
- split index by batch/dataset;
- keep vector index on SSD when needed.

## Runtime Access Rules

Search path:

```text
Query
  -> FAISS / SQLite FTS5
  -> row_id / doc_id
  -> SQLite metadata lookup
  -> return video_id, frame_id, paths, evidence
  -> UI lazy-loads thumbnails
```

Never do during live search:

- load all images;
- load all videos;
- scan the raw filesystem;
- run OCR/ASR/captioning.
