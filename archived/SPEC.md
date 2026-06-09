# SPEC.md — Multimedia Analysis & Retrieval Workspace

## 0. Purpose

This document is the technical specification for the AI Challenge 2026 project: a local-first, evidence-grounded multimedia analysis and retrieval workspace for large-scale video/image/audio/text data.

The application is designed for competition use, research iteration, and team-based retrieval workflows. It must support human-in-the-loop operation, structured query solving, evidence inspection, timeline navigation, and eventually bounded agent automation.

The product is not a chatbot and not a simple video search UI. It is a workspace for retrieving, analyzing, verifying, and deciding on multimedia evidence.

---

## 1. Product Definition

### 1.1 Product Name

Working name:

```text
AIC Multimedia Retrieval Workspace
```

Alternative internal codename:

```text
MARS — Multimedia Analysis & Retrieval System
```

### 1.2 Product Goal

Build a competition-grade application that helps a team solve AI Challenge 2026 query tasks faster and more accurately by combining:

- multimedia data ingestion;
- visual, text, OCR, ASR, caption, and temporal retrieval;
- evidence-grounded result inspection;
- query-type-specific solvers;
- Warp-inspired block workspace UI;
- evaluation and mock contest workflow;
- bounded auto-agent support.

### 1.3 Primary Users

| User | Purpose |
|---|---|
| Operator | Runs queries, inspects results, selects candidates quickly. |
| Query Analyst | Decomposes query clues, suggests search strategies. |
| Evidence Checker | Reviews OCR, ASR, captions, timeline, and candidate validity. |
| System/ML Engineer | Builds indexes, monitors pipelines, debugs errors. |
| Auto-Agent | Programmatically parses query, calls tools, ranks candidates, logs decisions. |

### 1.4 Supported Query Types

| Query Type | Meaning | Core Need |
|---|---|---|
| KIS | Textual Known Item Search | Find the correct video/frame/segment from a natural-language description. |
| Q&A | Visual/Multimedia Question Answering | Retrieve the relevant event and answer a question using evidence. |
| TRAKE | Temporal Retrieval and Alignment of Key Events | Find ordered frames/events in a video timeline. |
| VKIS | Video/Visual Known Item Search | Operator watches a short clip, describes it, and searches from memory. |

### 1.5 Non-Goals for Early Versions

Do not prioritize these in the first milestone:

- full autonomous agent as the main interface;
- cloud-first deployment;
- polished commercial UI;
- training custom models from scratch;
- distributed microservices architecture;
- submission-file workflow as the central architecture concept;
- complex multi-user collaboration state before core retrieval is stable.

---

## 2. Design Principles

### 2.1 Evidence-First

Every candidate must be explainable by evidence.

A candidate should show:

- visual score;
- matched captions;
- matched OCR;
- matched ASR;
- object/concept matches;
- timeline context;
- model/source confidence.

Rationale: competition decisions are made by humans under time pressure. A result without evidence forces manual inspection and slows the team.

### 2.2 Frame-Centric, Shot-Aware

The core grounding unit is the frame/keyframe because most retrieval tasks require frame-level or timestamp-level decisions.

However, search results should be grouped by shot/segment to reduce near-duplicate frames.

```text
Video → Shot/Segment → Frame → Evidence
```

### 2.3 Hybrid Retrieval by Default

No single retrieval signal is sufficient. The system should combine:

- visual embedding search;
- caption search;
- OCR search;
- ASR transcript search;
- object/concept search;
- entity search;
- temporal/timeline search;
- optional reranking and verification.

### 2.4 Workspace-First UI

The UI should feel like a power-user workspace inspired by Warp:

- blocks;
- command palette;
- panels;
- run history;
- logs;
- inspector;
- keyboard-first actions.

It should not behave like a single chat window.

### 2.5 Human and Agent Share the Same Core

Human UI and auto-agent must call the same retrieval, solver, and evidence APIs.

```text
Human UI ─────┐
              ├── Retrieval / Analysis Core
Auto Agent ───┘
```

### 2.6 Local-First, LAN-Capable

The system must run locally/offline on a powerful machine. It should also support LAN access for team usage.

Default target:

```text
Local machine or LAN server with dataset, index, and model workers.
```

Cloud hosting is optional and not required for the competition workflow.

---

## 3. Recommended Architecture

### 3.1 High-Level Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│ Workspace UI                                                 │
│ Query blocks, result grid, video/timeline inspector, logs    │
├─────────────────────────────────────────────────────────────┤
│ Interaction / Decision Layer                                 │
│ pin, reject, compare, accept, annotate, replay               │
├─────────────────────────────────────────────────────────────┤
│ Query Solvers                                                │
│ KIS Solver, Q&A Solver, TRAKE Solver, VKIS Solver            │
├─────────────────────────────────────────────────────────────┤
│ Retrieval & Analysis Core                                    │
│ query parsing, search planning, fusion, rerank, verification │
├─────────────────────────────────────────────────────────────┤
│ Index Layer                                                  │
│ visual vectors, text, OCR, ASR, object, entity, timeline     │
├─────────────────────────────────────────────────────────────┤
│ Evidence Layer                                               │
│ captions, OCR, ASR, object labels, entities, actions, scenes │
├─────────────────────────────────────────────────────────────┤
│ Media & Data Foundation                                      │
│ videos, keyframes, frames, shots, thumbnails, metadata       │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Runtime Shape

The preferred runtime architecture is hybrid/local-first.

```text
Workspace UI
  ↓
App Core API
  ↓
Retrieval Core
  ├── Vector index
  ├── Text index
  ├── Metadata store
  ├── Media store
  └── AI workers
```

The UI can run as:

- local browser UI;
- LAN-accessible web UI;
- desktop shell wrapper later if desired.

The core should not depend on the shell choice.

### 3.3 Suggested Tech Stack

The stack should optimize for speed of development, local-first execution, retrieval performance, and future desktop wrapping.

#### Frontend

| Need | Suggested Tool |
|---|---|
| Workspace UI | React + TypeScript |
| Styling | Tailwind CSS |
| State | Zustand or similar local state |
| Data fetching | TanStack Query or custom API client |
| Grid virtualization | TanStack Virtual / react-window |
| Video player | HTML5 video with custom controls |
| Desktop wrapper later | Tauri optional |

#### Backend / Core

| Need | Suggested Tool |
|---|---|
| API | FastAPI or Rust API layer |
| Local-first orchestration | Rust core optional, Python acceptable for early MVP |
| Metadata DB | PostgreSQL for LAN/server mode, SQLite acceptable for pure local prototype |
| Text search | OpenSearch for easy setup or Tantivy for embedded/local performance |
| Vector search | FAISS first |
| Evaluation analytics | DuckDB + Parquet |
| Cache | Redis optional; in-memory cache acceptable for v0 |
| Media processing | FFmpeg |
| AI workers | Python/PyTorch/ONNX workers |

#### AI/ML

| Need | Suggested Tool / Model Family |
|---|---|
| Visual embeddings | CLIP / SigLIP / EVA-CLIP / BTC-provided embeddings |
| Text embeddings | bge-m3 / multilingual-e5 / Jina multilingual embeddings |
| OCR | PaddleOCR / VietOCR / BTC-provided OCR if available |
| ASR | Whisper / Vietnamese ASR / BTC-provided transcript if available |
| Captioning | Qwen-VL / InternVL / LLaVA-family / BLIP-family |
| Reranking | Cross-encoder, bge-reranker, LVLM verification for top-K |
| Agent | Bounded tool-calling controller, not free-form chatbot |

### 3.4 Tech Stack Decision

Default implementation recommendation:

```text
Frontend: React + TypeScript + Tailwind
Core/API: FastAPI initially, Rust modules optional later
Media: local filesystem + FFmpeg
Metadata: PostgreSQL for team/server mode
Vector: FAISS
Text: OpenSearch initially, Tantivy optional if embedded/local is preferred
Eval: DuckDB + Parquet
AI: Python workers
Deployment: local or LAN server
```

Rationale:

- React is ideal for complex workspace UI.
- Python AI ecosystem is strongest for embeddings, OCR, ASR, and LVLM.
- FAISS is fast and local-friendly.
- PostgreSQL handles metadata, workspace state, and run history well.
- OpenSearch/Tantivy handles full-text evidence search better than pure SQL at scale.
- DuckDB/Parquet is ideal for evaluation and offline analytics.

Tradeoff:

- More components than a simple app.
- But each component handles the data type it is best suited for.

---

## 4. Hosting and Team Usage Strategy

### 4.1 Modes

#### Mode 1: Solo Local Mode

Used during early development.

```text
http://localhost:3000
```

Everything runs on one machine:

- UI;
- backend/core;
- metadata DB;
- indexes;
- media files;
- AI workers if hardware allows.

#### Mode 2: LAN Team Mode

Used during team practice and contest simulation.

```text
Main machine/server: 192.168.x.x
Teammates open browser to: http://192.168.x.x:3000
```

One powerful machine hosts:

- dataset;
- indexes;
- GPU workers;
- metadata DB;
- workspace server;
- UI server.

Team members use laptops as clients.

#### Mode 3: Cloud Mode

Optional only for remote collaboration. Not recommended as default due to:

- dataset upload cost;
- network dependency;
- latency;
- possible contest internet constraints.

### 4.2 Recommended Competition Setup

```text
Primary machine/server:
- dataset on NVMe
- indexes loaded locally
- backend/core running
- UI served over LAN
- optional GPU workers

Client machines:
- browser only
- no dataset copy required
```

### 4.3 Tradeoffs

| Option | Pros | Cons |
|---|---|---|
| Desktop-only | Native feel, easy file access | Harder multi-user, harder GPU/server separation |
| Local web | Fast dev, simple, local-first | Less native feel |
| LAN web | Best for team usage | Needs local network/server setup |
| Cloud | Remote access | Costly, latency, dataset transfer, internet dependency |

Decision: build core as web/API-compatible first, keep desktop shell optional.

---

## 5. Data Model

### 5.1 Core Entities

```text
Dataset
Video
Shot
Frame
MediaAsset
Evidence
EmbeddingRef
IndexVersion
QueryBlock
RetrievalRun
SearchPlan
Candidate
UserDecision
AgentTrace
EvalRun
```

### 5.2 Entity Relationships

```text
Dataset 1──N Video
Video   1──N Shot
Video   1──N Frame
Shot    1──N Frame
Frame   1──N Evidence
Frame   1──N EmbeddingRef
QueryBlock 1──N RetrievalRun
RetrievalRun 1──N Candidate
Candidate N──N Evidence
QueryBlock 1──N UserDecision
RetrievalRun 1──N AgentTrace
```

### 5.3 Video

Represents a source video.

Fields:

```text
id
video_name
path
duration_sec
fps
width
height
source_dataset_id
hash
metadata
created_at
```

### 5.4 Shot / Segment

Represents a continuous segment or scene group.

Fields:

```text
id
video_id
shot_id
start_frame_id
end_frame_id
start_time_sec
end_time_sec
representative_frame_id
metadata
```

### 5.5 Frame

Main grounding unit.

Fields:

```text
id
video_id
frame_id
timestamp_sec
shot_id
frame_path
thumbnail_path
metadata
```

### 5.6 Evidence

Evidence extracted from media.

Fields:

```text
id
video_id
frame_id nullable
shot_id nullable
start_time_sec nullable
end_time_sec nullable
type
content
normalized_content
confidence
source_model
bbox nullable
metadata
created_at
```

Evidence types:

```text
caption
dense_caption
ocr
asr
object
entity
action
scene
audio_event
relationship
manual_note
```

### 5.7 EmbeddingRef

Maps vectors to domain objects.

Fields:

```text
id
entity_type        # frame, shot, evidence, asr_segment, caption
entity_id
embedding_model
vector_index_name
vector_id
dimension
created_at
metadata
```

### 5.8 QueryBlock

A workspace block for one query.

Fields:

```text
id
workspace_id
query_id
query_type        # kis, qa, trake, vkis
original_text
language
status
parsed_intent
active_run_id
created_at
updated_at
```

### 5.9 RetrievalRun

One run of a solver/search strategy.

Fields:

```text
id
query_block_id
solver_name
status
search_plan
config
model_versions
index_versions
latency_ms
created_at
```

### 5.10 Candidate

A retrieval result.

Fields:

```text
id
run_id
rank
video_id
frame_id nullable
shot_id nullable
timestamp_sec nullable
score
confidence
source_scores
explanation
evidence_refs
metadata
```

### 5.11 UserDecision

Operator action.

Fields:

```text
id
query_block_id
candidate_id
action        # pin, reject, accept, compare, note
note
created_by
created_at
```

### 5.12 AgentTrace

Logs agent decision steps.

Fields:

```text
id
run_id
step_index
step_type
message
tool_name nullable
input
output
latency_ms
created_at
```

---

## 6. Storage Strategy

### 6.1 Storage by Data Type

| Data | Storage |
|---|---|
| Raw videos | Local filesystem / object storage |
| Keyframes / thumbnails | Local filesystem / object storage |
| Metadata / workspace / runs | PostgreSQL |
| Text evidence canonical | PostgreSQL |
| Text evidence search | OpenSearch or Tantivy |
| Visual embeddings | FAISS index + mapping table/file |
| Raw vector artifacts | `.npy`, `.parquet`, or binary artifacts |
| Evaluation datasets | DuckDB + Parquet |
| Logs/traces | JSONL + DB summaries |
| Cached media | Local filesystem |

### 6.2 Filesystem Layout

```text
data/
  raw/
    videos/
    keyframes/
    metadata/
    queries/
  processed/
    frames/
    thumbnails/
    clips/
    contact_sheets/
    ocr/
    asr/
    captions/
  indexes/
    faiss/
    text/
  eval/
    queries/
    ground_truth/
    predictions/
    metrics/
  runs/
    retrieval/
    agent/
    mock_contests/
  logs/
```

### 6.3 Source of Truth Rules

- Raw media files are immutable.
- Processed artifacts are reproducible.
- PostgreSQL stores canonical metadata and app state.
- Search indexes are rebuildable acceleration layers.
- Evaluation results are versioned.
- Each candidate must trace back to evidence and media.

---

## 7. Ingestion Pipeline

### 7.1 Pipeline Overview

```text
Raw dataset
→ dataset registration
→ video registration
→ keyframe/frame extraction or import
→ thumbnail generation
→ shot/segment detection
→ evidence extraction/import
→ embedding generation/import
→ index building
→ validation report
```

### 7.2 Step 1: Dataset Registration

Input:

```text
dataset path
metadata path
version name
```

Output:

```text
Dataset record
folder manifest
file count report
```

Validation:

- video files exist;
- keyframe folders match video names;
- metadata files readable;
- no duplicate video names unless intended.

### 7.3 Step 2: Video Registration

For each video:

- read path;
- extract duration;
- extract FPS;
- extract resolution;
- compute optional hash;
- create `Video` record.

### 7.4 Step 3: Frame / Keyframe Registration

If keyframes are provided:

- import keyframe image paths;
- parse frame ids;
- map to video;
- map timestamp if metadata is available.

If not provided:

- extract frames every N seconds or using scene detection;
- assign internal frame ids;
- store frame images.

### 7.5 Step 4: Thumbnail Generation

For UI speed:

- resize frame images;
- convert to WebP/JPEG;
- store fixed-size thumbnails;
- keep path in `Frame.thumbnail_path`.

### 7.6 Step 5: Shot / Segment Detection

v0:

- time-window grouping;
- or group consecutive keyframes.

v1:

- scene cut detection;
- representative frame selection.

### 7.7 Step 6: Evidence Import / Extraction

Extract or import:

- captions;
- OCR;
- ASR;
- object labels;
- scene tags;
- entities;
- actions if available.

### 7.8 Step 7: Embedding Generation / Import

Generate or import:

- visual embeddings for frames/shots;
- text embeddings for captions/evidence;
- ASR embeddings if useful.

### 7.9 Step 8: Build Indexes

Build:

- visual FAISS index;
- text evidence index;
- OCR index;
- ASR index;
- caption index;
- entity/object index.

### 7.10 Step 9: Validation Report

Report:

```text
number of videos
number of frames
missing thumbnails
missing timestamps
OCR coverage
ASR coverage
caption coverage
embedding coverage
index size
broken paths
```

---

## 8. Evidence Extraction Strategy

### 8.1 Priority Order

Prioritize extraction in this order:

1. import BTC-provided metadata if available;
2. generate thumbnails and frame registry;
3. visual embeddings;
4. OCR;
5. ASR;
6. captions;
7. object/entity extraction;
8. dense captions and LVLM-derived evidence;
9. action/relationship extraction.

### 8.2 Incremental Extraction

Do not require all evidence before using the system.

The system must tolerate partial coverage:

```text
frame A has visual + OCR
frame B has visual + caption
video C has ASR only
```

### 8.3 Evidence Normalization

Normalize text evidence:

- lowercase;
- remove repeated whitespace;
- optional accent-stripped version;
- language detection if feasible;
- store both raw and normalized content.

### 8.4 OCR Strategy

OCR should store:

```text
raw text
normalized text
bbox
confidence
frame_id
source_model
```

OCR is critical for:

- signs;
- slides;
- labels;
- brand names;
- TV captions;
- location names.

### 8.5 ASR Strategy

ASR should store:

```text
start_time_sec
end_time_sec
transcript
confidence
language
nearest frame ids
```

ASR is critical for:

- speeches;
- interviews;
- named entities;
- spoken answers;
- Q&A retrieval.

### 8.6 Caption Strategy

Captioning should start at representative frames/shots, not every frame.

Caption granularity:

| Granularity | Use |
|---|---|
| frame caption | visual detail |
| shot caption | event-level description |
| dense caption | advanced reranking |

### 8.7 Object / Entity Strategy

Object labels can come from:

- BTC metadata;
- detector outputs;
- captions parsed into nouns;
- LVLM structured output.

Entity tags can come from:

- OCR NER;
- ASR NER;
- caption NER;
- query expansion.

---

## 9. Indexing Strategy

### 9.1 Index Types

| Index | Purpose |
|---|---|
| visual_frame_index | retrieve frame by visual/text embedding |
| visual_shot_index | retrieve representative shot candidates |
| caption_index | retrieve by caption/description |
| ocr_index | retrieve by on-screen text |
| asr_index | retrieve by transcript |
| object_index | filter by concepts/objects |
| entity_index | retrieve by people/places/orgs |
| timeline_index | retrieve nearby frames and temporal order |

### 9.2 FAISS Visual Index

Store:

```text
index.faiss
ids.parquet or db mapping
config.json
```

Mapping must include:

```text
vector_id
video_name
frame_id
timestamp_sec
shot_id
embedding_model
```

### 9.3 Text Search Index

Each evidence document should contain:

```text
evidence_id
video_name
frame_id
shot_id
timestamp_sec
type
content
normalized_content
confidence
source_model
```

### 9.4 Index Versioning

Each index must have version metadata:

```text
index_name
source_dataset
source_tables
model_name
created_at
num_items
dimension if vector
config_hash
```

### 9.5 Rebuild Policy

Indexes are rebuildable. Do not manually edit indexes. Rebuild from canonical metadata and artifacts.

---

## 10. Retrieval Pipeline

### 10.1 Generic Retrieval Flow

```text
input query
→ query parser
→ query type classifier
→ clue extraction
→ search planner
→ parallel retrieval tools
→ candidate merge
→ score fusion
→ grouping/diversification
→ rerank top-K
→ attach evidence
→ return candidates
```

### 10.2 Query Parser Output

```json
{
  "query_type": "kis",
  "language": "vi",
  "visual_clues": [],
  "ocr_clues": [],
  "asr_clues": [],
  "entity_clues": [],
  "temporal_clues": [],
  "answer_constraints": {},
  "events": []
}
```

### 10.3 Search Plan

```json
{
  "tools": [
    {"name": "visual_search", "weight": 0.4, "top_k": 200},
    {"name": "caption_search", "weight": 0.25, "top_k": 200},
    {"name": "ocr_search", "weight": 0.2, "top_k": 100},
    {"name": "asr_search", "weight": 0.15, "top_k": 100}
  ],
  "rerank": true,
  "diversify_by": ["video", "shot"]
}
```

### 10.4 Fusion

v0:

```text
weighted sum over normalized source scores
```

v1:

```text
reciprocal rank fusion + source-specific boosts
```

v2:

```text
learned reranker or LLM/LVLM verification on top-K
```

### 10.5 Candidate Diversification

Prevent duplicate-heavy results by grouping:

- same video;
- same shot;
- nearby frame window;
- identical evidence match.

### 10.6 Evidence Attachment

Each candidate should return:

```text
matched evidence ids
source scores
short explanation
thumbnail/video URL
timeline context
```

---

## 11. Query Solvers

### 11.1 KIS Solver

Purpose: find a known video/frame/event from textual description.

Flow:

```text
long description
→ clue extraction
→ hybrid search
→ evidence scoring
→ candidate diversification
→ top candidates
```

UI:

- query block;
- parsed clues;
- result grid;
- evidence inspector;
- similar frames;
- nearby timeline.

### 11.2 Q&A Solver

Purpose: retrieve event and answer question.

Flow:

```text
description + question
→ split retrieval description and answer question
→ retrieve candidates
→ inspect nearby evidence
→ extract answer candidates
→ normalize answer
→ show answer evidence
```

Answer candidate fields:

```text
raw_answer
normalized_answer
source_evidence
confidence
normalization_rules
```

### 11.3 TRAKE Solver

Purpose: retrieve and align ordered events.

Flow:

```text
event sequence
→ parse E1...EN
→ retrieve candidate videos
→ search frames per event
→ enforce same-video constraint
→ enforce chronological order
→ score sequence
→ show timeline alignment
```

Sequence scoring should consider:

- per-event match score;
- chronological validity;
- temporal spacing;
- same-video consistency;
- evidence coverage.

### 11.4 VKIS Solver

Purpose: allow operator to search from memory after viewing a short video.

Flow:

```text
memory capture form
→ structured query
→ generated query variants
→ hybrid retrieval
→ visual confirmation
```

Memory form fields:

```text
scene
objects
people
actions
colors
text seen
audio heard
location clues
distinctive details
```

---

## 12. Workspace UI Specification

### 12.1 Layout

```text
┌──────────────────────────────────────────────────────────────┐
│ Top Bar / Command Palette                                    │
├───────────────┬───────────────────────────┬──────────────────┤
│ Left Sidebar  │ Main Workspace             │ Right Inspector  │
│ Query/session │ Query blocks/result views  │ Video/evidence   │
├───────────────┴───────────────────────────┴──────────────────┤
│ Bottom Panel: logs, jobs, metrics, system                     │
└──────────────────────────────────────────────────────────────┘
```

### 12.2 Top Bar

Components:

- command palette;
- global query input;
- mode switcher;
- run button;
- index status;
- latency indicator.

### 12.3 Left Sidebar

Components:

- workspace selector;
- query list;
- query type filter;
- status filter;
- pinned candidates;
- run history;
- saved searches.

### 12.4 Main Workspace

Components:

- QueryBlock;
- RunBlock;
- AgentRunBlock;
- ResultGrid;
- CandidateCard;
- CandidateTray;
- CompareView;
- ParsedIntentView;
- SearchPlanView.

### 12.5 Right Inspector

Components:

- VideoPreview;
- FrameViewer;
- TimelineViewer;
- EvidencePanel;
- OCRPanel;
- ASRPanel;
- CaptionPanel;
- ObjectPanel;
- MetadataPanel;
- ScoreBreakdown.

### 12.6 Bottom Panel

Tabs:

- Logs;
- Jobs;
- Metrics;
- Errors;
- System.

### 12.7 Query-Type Specific UI

| Query Type | Components |
|---|---|
| KIS | Parsed clues, result grid, evidence matches |
| Q&A | Answer panel, answer candidates, normalization preview |
| TRAKE | Event slots, timeline alignment, per-event candidates |
| VKIS | Memory capture form, chips, query variants |

### 12.8 Keyboard Shortcuts

Suggested:

| Shortcut | Action |
|---|---|
| Ctrl/Cmd+K | Open command palette |
| Enter | Run search |
| 1-9 | Open candidate |
| A | Add/pin candidate |
| R | Rerun block |
| F | Find similar |
| T | Open timeline |
| E | Toggle evidence |
| G | Group by video/shot |
| Esc | Close active overlay |

---

## 13. API / Core Interface Specification

### 13.1 Workspace APIs

```http
POST /workspaces
GET  /workspaces/:id
POST /query-blocks
GET  /query-blocks/:id
PATCH /query-blocks/:id
```

### 13.2 Search / Run APIs

```http
POST /query-blocks/:id/parse
POST /query-blocks/:id/run
POST /query-blocks/:id/rerank
POST /query-blocks/:id/find-similar
GET  /runs/:id
GET  /runs/:id/candidates
```

### 13.3 Media APIs

```http
GET /videos
GET /videos/:videoName
GET /videos/:videoName/frames
GET /videos/:videoName/frame/:frameId
GET /videos/:videoName/timeline?centerFrame=...
GET /assets/thumbnail/:frameId
```

### 13.4 Evidence APIs

```http
GET /frames/:frameId/evidence
GET /videos/:videoName/evidence?start=...&end=...
GET /candidates/:id/evidence
```

### 13.5 Evaluation APIs

```http
POST /eval/runs
GET  /eval/runs/:id
GET  /eval/runs/:id/metrics
GET  /eval/runs/:id/errors
```

---

## 14. Evaluation Specification

### 14.1 Evaluation Dataset

The internal benchmark must include:

- KIS queries;
- Q&A queries;
- TRAKE queries;
- VKIS-style practice queries.

### 14.2 Metrics

#### KIS

```text
Recall@1
Recall@10
Recall@50
Recall@100
Video accuracy
Frame tolerance accuracy
```

#### Q&A

```text
Retrieval accuracy
Answer exact/normalized accuracy
End-to-end correctness
```

#### TRAKE

```text
Video accuracy
Per-event accuracy
Sequence accuracy
Chronological validity
```

#### VKIS

```text
Time-to-description
Time-to-first-candidate
Time-to-answer
Operator error rate
```

#### System

```text
Search latency p50/p95
Thumbnail load time
Video seek time
Crash rate
Index load time
```

### 14.3 Error Taxonomy

```text
retrieval_miss
rerank_wrong
query_parse_wrong
answer_wrong
temporal_alignment_wrong
evidence_missing
operator_missed
ui_slow
index_error
media_path_error
system_crash
```

---

## 15. Agent Specification

### 15.1 Agent Role

The agent is a bounded controller, not the primary UI and not a free-form chatbot.

### 15.2 Agent Loop

```text
classify query
→ parse constraints
→ generate search plan
→ call retrieval tools
→ merge candidates
→ rerank/verify
→ compute confidence
→ return candidates and trace
```

### 15.3 Agent Constraints

The agent must:

- call explicit tools;
- log every step;
- return structured output;
- be replayable;
- allow human override;
- not hide reasoning-critical evidence.

### 15.4 Agent Trace UI

Agent runs appear as workspace blocks with:

- parsed query;
- search plan;
- tool calls;
- candidate ranking;
- final recommendation;
- confidence;
- logs.

---

## 16. Performance Targets

| Operation | Target |
|---|---:|
| Lightweight hybrid search | < 1-2 seconds |
| First results visible | < 1 second after search completes |
| Thumbnail grid render | < 1-2 seconds for top candidates |
| Video seek near frame | < 1 second if local cached |
| Timeline nearby frames | near-instant after assets loaded |
| Heavy rerank | async / progressive |
| App startup with existing indexes | acceptable within contest setup time |

---

## 17. Phase Roadmap

### Phase 0: Product and Architecture Definition

Deliverables:

- `ARCHITECTURE.md`
- `DATA_MODEL.md`
- `UI_WORKSPACE.md`
- `ROADMAP.md`
- initial backlog

Tasks:

- define roles;
- define query types;
- define domain model;
- define UI wireframe;
- define data lifecycle;
- define P0/P1/P2.

### Phase 1: Data Foundation

Deliverables:

- dataset registry;
- video registry;
- frame registry;
- thumbnail store;
- basic dataset browser.

Acceptance criteria:

```text
open app
→ view videos
→ view frames
→ click frame
→ open correct timestamp
```

### Phase 2: Evidence Extraction

Deliverables:

- evidence schema;
- OCR evidence;
- ASR evidence;
- caption evidence;
- evidence inspector.

Acceptance criteria:

```text
click frame
→ see available OCR/ASR/caption/object evidence
```

### Phase 3: Search Baseline

Deliverables:

- visual search;
- text evidence search;
- OCR search;
- ASR search;
- hybrid fusion;
- candidate object.

Acceptance criteria:

```text
input query
→ top candidates with thumbnails, scores, evidence
```

### Phase 4: Workspace UI v1

Deliverables:

- app shell;
- query sidebar;
- query block;
- result grid;
- right inspector;
- timeline viewer;
- candidate tray;
- logs panel.

Acceptance criteria:

```text
operator can run query, inspect candidates, pin/reject candidates, and view evidence
```

### Phase 5: KIS Solver + Evaluation v0

Deliverables:

- KIS solver;
- parsed clues view;
- KIS benchmark;
- metrics report.

Acceptance criteria:

```text
run internal KIS benchmark and get Recall@K metrics
```

### Phase 6: Q&A Mode

Deliverables:

- Q&A parser;
- answer panel;
- answer candidates;
- answer normalization;
- Q&A evaluation.

Acceptance criteria:

```text
Q&A query returns candidate video/frame and answer candidates with evidence
```

### Phase 7: TRAKE Mode

Deliverables:

- event parser;
- event slot UI;
- temporal alignment view;
- sequence scorer;
- TRAKE evaluation.

Acceptance criteria:

```text
TRAKE query returns candidate video and ordered event frames on timeline
```

### Phase 8: VKIS Mode

Deliverables:

- memory capture form;
- generated query variants;
- VKIS mode;
- VKIS practice workflow.

Acceptance criteria:

```text
operator can describe a watched clip and retrieve plausible candidates quickly
```

### Phase 9: Reranking and Agent Skeleton

Deliverables:

- reranker;
- query expansion;
- evidence verifier;
- bounded agent controller;
- agent run block;
- replay run.

Acceptance criteria:

```text
agent can parse query, generate search plan, call tools, return ranked candidates with trace
```

### Phase 10: Performance and Contest Hardening

Deliverables:

- performance report;
- optimized thumbnail/video loading;
- hotkeys;
- stable app build;
- mock contest dashboard;
- runbook.

Acceptance criteria:

```text
system runs stable during mock contest and supports fast operator workflow
```

---

## 18. P0 / P1 / P2 Backlog

### P0

- video/frame registry;
- thumbnail generation;
- frame/timestamp mapping;
- evidence schema;
- OCR/caption/ASR import or generation;
- visual search baseline;
- text evidence search;
- hybrid fusion v0;
- candidate object with evidence;
- query block UI;
- result grid;
- video inspector;
- evidence panel;
- KIS solver v0;
- evaluation set v0.

### P1

- query decomposition;
- source score breakdown;
- candidate diversification;
- Q&A solver;
- answer panel;
- TRAKE solver v0;
- timeline alignment UI;
- VKIS memory form;
- candidate tray;
- compare view;
- run history;
- mock contest dashboard;
- hotkeys.

### P2

- LVLM reranker;
- dense caption generation;
- advanced query expansion;
- evidence verifier;
- bounded auto-agent;
- agent run block;
- advanced temporal reasoning;
- multi-user/LAN collaboration state;
- model/index version tracking;
- ablation dashboard.

---

## 19. Coding Principles

### 19.1 Domain-First

Code should revolve around domain entities, not UI screens or model scripts.

Core types:

```text
Video
Frame
Shot
Evidence
QueryBlock
RetrievalRun
Candidate
SearchPlan
UserDecision
AgentTrace
```

### 19.2 Evidence Traceability

Every candidate must trace to evidence and media.

### 19.3 Replayability

Every retrieval run should be replayable with:

```text
same query
same config
same index version
same model version
```

### 19.4 Config-Driven

Do not hardcode:

- paths;
- top-K;
- fusion weights;
- model names;
- index names;
- rerank settings.

### 19.5 Interface-Based Retrieval

Each retrieval tool should expose the same conceptual interface:

```text
search(request) → candidates
```

### 19.6 UI Must Not Contain Business Logic

UI renders and controls state. Retrieval, solver logic, reranking, agent logic, and evaluation live in core modules/services.

### 19.7 Structured Logging

Every run should log:

- query id;
- run id;
- solver;
- search tools called;
- latency;
- candidate count;
- errors;
- config;
- model/index versions.

### 19.8 Progressive Complexity

Build in this order:

```text
baseline → evidence → evaluation → rerank → agent → optimization
```

Do not invert the order.

---

## 20. Anti-Patterns

Avoid:

- building chatbot first;
- building polished UI before data/search works;
- fine-tuning models before evaluation exists;
- making submission files the core domain;
- storing video blobs in the database;
- storing all vectors directly in relational DB at large scale;
- relying only on CLIP/vector search;
- creating many microservices too early;
- hiding evidence behind opaque scores;
- building agent logic before retrieval tools are reliable;
- using notebooks as production pipeline;
- not versioning indexes;
- not logging retrieval runs;
- not doing mock contests.

---

## 21. Final Direction

This project should be built as:

```text
local-first evidence-grounded multimedia retrieval workspace
```

Its core value is not a single model. Its value comes from:

```text
strong data foundation
+ evidence extraction
+ hybrid retrieval
+ fast workspace UI
+ query-specific solvers
+ evaluation loop
+ bounded agent automation
```

The guiding question for every feature is:

```text
Does this help the human or agent find, verify, and decide on the correct multimedia evidence faster and more reliably?
```
