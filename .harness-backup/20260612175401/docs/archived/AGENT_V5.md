# AGENT.md — AI Challenge 2026 Multimedia Retrieval Workspace

This file is the source of truth for AI coding agents working on this project. It defines the project goal, product shape, architecture direction, domain model, UI model, retrieval pipeline, roadmap, coding principles, and key tradeoffs.

## 1. Project Definition

We are building a local-first, evidence-grounded multimedia analysis and retrieval workspace for AI Challenge 2026.

The system is not a chatbot, not a simple video search page, and not a model demo. It is a competition-grade workspace where humans and agents can retrieve, inspect, compare, reason over, and select evidence from a large multimedia dataset.

The product should help solve these query types:

- Textual KIS: find the correct video/frame from a long natural-language description.
- Q&A: find the correct video/frame and answer a question using evidence from the video.
- TRAKE: retrieve and align a sequence of key events in temporal order.
- VKIS / Video KIS: the operator watches a short video/image query and describes it manually to search the dataset.

The project goal is:

```text
Find the right evidence quickly,
understand the query correctly,
retrieve the right video/frame/event sequence,
help the operator or agent verify the result,
and support fast decision-making under contest pressure.
```

The central product concept is:

```text
Evidence-grounded Multimedia Analysis & Retrieval Workspace
```

## 2. Core Product Principles

### 2.1 Evidence-first

Every candidate result must answer: why does this match the query?

A candidate should not only have a score. It should expose evidence such as:

- visual match: person, object, action, scene, color;
- OCR match: text visible in frame;
- ASR match: speech/transcript around the timestamp;
- caption match: short or dense visual description;
- object/concept match: detected objects or concepts;
- temporal match: event order and neighboring context.

Evidence is required for fast human verification, reranking, debugging, agent reasoning, and post-contest analysis.

### 2.2 Frame-centric, shot-aware

The core grounding unit is the frame because most outputs eventually need a frame/timestamp and the UI is thumbnail/frame-driven.

However, retrieval must be shot-aware or segment-aware to avoid returning many duplicate frames from the same moment.

Recommended mental model:

```text
Video
  -> Shot / Segment
      -> Frame
          -> Evidence
          -> Embeddings
          -> OCR
          -> Caption
          -> Linked ASR segment
```

Use frames for grounding and UI. Use shots/segments for grouping, diversification, and timeline navigation.

### 2.3 Hybrid retrieval, not single-model retrieval

Do not rely on a single vector model. The system must combine multiple retrieval signals:

- visual embeddings;
- captions;
- OCR;
- ASR/transcripts;
- object/concept labels;
- entity tags;
- scene/action tags;
- temporal context;
- query expansion.

Different query types require different signals. Visual-only retrieval will fail on OCR, ASR, Q&A, and temporal tasks.

### 2.4 Workspace-first, not chatbot-first

The UI should be a workspace inspired by Warp-style interaction patterns: block-based, command-driven, keyboard-first, inspectable, replayable.

The main workflow is:

```text
Query Block
  -> Search Run
  -> Candidate Grid
  -> Evidence Inspector
  -> Timeline Viewer
  -> Candidate Tray
  -> Human/Agent Decision
```

A chatbot UI is insufficient because the user needs to compare candidates, inspect videos, view timelines, pin/reject results, and replay runs.

### 2.5 Human and agent share the same retrieval core

Do not build separate systems for the UI and the auto-agent.

Both should call the same core modules:

```text
Query Parser
Search Planner
Retrieval Tools
Fusion Engine
Reranker
Evidence Verifier
```

The agent is an orchestration layer over the same tools humans use. Agent runs should be visible as workspace blocks and should be replayable/debuggable.

### 2.6 Local-first, server-capable

The system should run locally/offline first. It may later support LAN/server mode for team collaboration or GPU-heavy workloads.

Do not assume cloud hosting or public internet. Contest environments may restrict connectivity, and the dataset is too large to treat as a cloud-first asset.

## 3. Architecture Map

The system has seven conceptual layers:

```text
7. Workspace UI
   Query blocks, result grid, inspector, timeline, agent logs

6. Interaction / Decision Layer
   pin, reject, compare, accept, user decisions, review state

5. Query Solvers
   KIS Solver, Q&A Solver, TRAKE Solver, VKIS Solver

4. Retrieval & Analysis Core
   query parsing, search planning, hybrid search, fusion, rerank, verification

3. Index Layer
   visual index, text index, OCR index, ASR index, object/entity/timeline indexes

2. Evidence Layer
   captions, OCR, ASR, objects, entities, actions, scenes

1. Media & Data Foundation
   videos, frames, shots, thumbnails, timestamps, metadata
```

Each layer should be replaceable and testable. Do not couple UI directly to raw model/index implementations.

## 4. Key Domain Objects

The core domain should be built around these objects.

### Dataset

Represents a dataset release or internal practice dataset.

Fields may include:

- dataset_id;
- name;
- version;
- source;
- root_path;
- created_at;
- metadata.

### Video

Represents one source video.

Fields:

- video_id;
- video_name;
- path;
- duration_sec;
- fps;
- width;
- height;
- dataset_id;
- metadata.

### Shot / Segment

Represents a temporal segment of a video.

Fields:

- shot_id;
- video_id;
- start_frame;
- end_frame;
- start_time_sec;
- end_time_sec;
- representative_frame_id;
- metadata.

### Frame

Primary grounding unit.

Fields:

- frame_id;
- video_id;
- video_name;
- frame_index;
- timestamp_sec;
- shot_id;
- frame_path;
- thumbnail_path;
- metadata.

### Evidence

Everything the system extracted or imported from multimedia.

Fields:

- evidence_id;
- video_id;
- video_name;
- frame_id, optional;
- shot_id, optional;
- start_time_sec, optional;
- end_time_sec, optional;
- evidence_type: caption, dense_caption, ocr, asr, object, entity, action, scene, relationship;
- content;
- normalized_content;
- confidence;
- source_model;
- metadata.

### QueryBlock

A workspace block representing a query or query variant.

Fields:

- block_id;
- workspace_id;
- query_id;
- query_type: kis, qa, trake, vkis;
- original_query;
- parsed_intent;
- status;
- active_run_id;
- created_at;
- updated_at.

### RetrievalRun

One execution of a query/search/solver.

Fields:

- run_id;
- block_id;
- solver_name;
- search_plan;
- config;
- model_versions;
- index_versions;
- status;
- latency_ms;
- logs;
- created_at.

### Candidate

A possible result returned by retrieval or solver.

Fields:

- candidate_id;
- run_id;
- video_name;
- frame_id;
- timestamp_sec;
- shot_id;
- rank;
- score;
- confidence;
- source_scores;
- evidence_refs;
- explanation;
- metadata.

### SearchPlan

A structured plan for which tools to call and why.

Fields:

- query_type;
- visual_terms;
- text_terms;
- ocr_terms;
- asr_terms;
- entities;
- temporal_events;
- tools_to_run;
- fusion_weights;
- rerank_policy.

### UserDecision

Human review actions.

Fields:

- decision_id;
- block_id;
- candidate_id;
- action: pin, reject, accept, compare, note;
- note;
- created_at;
- user_id, optional.

### AgentTrace

Step-by-step agent execution log.

Fields:

- trace_id;
- run_id;
- step_index;
- step_type;
- input;
- output;
- latency_ms;
- error, optional.

## 5. Data and Storage Strategy

Use storage based on data nature. Do not force all data into one database.

Recommended storage categories:

```text
Media files          -> local filesystem or object storage
Metadata/workspace   -> relational store
Evidence canonical   -> relational store + text index
Vector embeddings    -> vector index + mapping table
Text retrieval       -> full-text index
Evaluation           -> DuckDB/Parquet-style analytical storage
Logs/traces          -> JSONL + database summaries
```

### Raw Media

Store videos, keyframes, thumbnails, extracted frames, clips, and contact sheets as files. Do not store large binary media inside the relational database.

Suggested folder convention:

```text
data/
  raw/
    videos/
    keyframes/
    metadata/
  processed/
    frames/
    thumbnails/
    clips/
    contact_sheets/
  indexes/
  eval/
  runs/
```

### Canonical Metadata

Store video/frame/shot/evidence/workspace/run/candidate state in a relational database or equivalent structured local store. Keep JSON metadata flexible but do not make everything opaque JSON.

### Indexes

Indexes are acceleration layers. They must be rebuildable from canonical data.

Index types:

- visual vector index;
- text/caption index;
- OCR index;
- ASR index;
- object/concept index;
- entity index;
- timeline index.

Every index version should record:

- dataset version;
- model version;
- number of items;
- dimension if vector index;
- build config;
- created_at;
- source tables/files.

## 6. Retrieval Pipeline

The general retrieval pipeline is:

```text
Input query
  -> classify query type
  -> parse/decompose query
  -> extract clues
  -> build search plan
  -> run retrieval tools
  -> merge candidates
  -> group/diversify candidates
  -> rerank top-K
  -> attach evidence
  -> return candidates
```

### Query Parsing

The parser should extract:

- query type;
- visual clues;
- OCR clues;
- ASR clues;
- objects;
- actions;
- colors;
- scenes;
- entities;
- temporal constraints;
- answer constraints for Q&A;
- event list for TRAKE.

### Retrieval Tools

Every retrieval tool should expose a consistent interface:

```text
search(request) -> list[Candidate]
```

Tools include:

- VisualSearch;
- CaptionSearch;
- OCRSearch;
- ASRSearch;
- ObjectSearch;
- EntitySearch;
- TimelineSearch;
- SimilarFrameSearch.

### Fusion

Begin with simple rule-based weighted fusion. Later add learned/reranker-based fusion only if evaluation proves it helps.

Candidate source scores should remain visible. Never collapse all signal into a black-box score without explainability.

### Reranking

Reranking should operate on top-K candidates only. Do not run expensive LVLM/LLM verification over the entire dataset.

Useful reranking signals:

- exact OCR/ASR match;
- caption-query similarity;
- visual-query similarity;
- multi-signal agreement;
- query clue coverage;
- temporal consistency;
- diversity/grouping penalty.

## 7. Query Solvers

### KIS Solver

Purpose: find the correct video/frame from a long textual event description.

Pipeline:

```text
long query
  -> clue decomposition
  -> hybrid retrieval
  -> evidence matching
  -> candidate diversification
  -> ranked candidates
```

UI needs:

- parsed clues view;
- result grid;
- evidence match summary;
- similar frames;
- nearby timeline.

### Q&A Solver

Purpose: retrieve the correct video/frame and answer a question from the evidence.

Pipeline:

```text
description + question
  -> separate retrieval description from question
  -> retrieve candidates
  -> inspect evidence around candidates
  -> generate answer candidates
  -> normalize answer
  -> return answer with evidence
```

UI needs:

- question panel;
- answer candidates;
- answer evidence;
- normalized answer view;
- confidence and source evidence.

### TRAKE Solver

Purpose: retrieve a sequence of event frames in temporal order.

Pipeline:

```text
event sequence
  -> parse events E1..EN
  -> find candidate videos
  -> search frames per event
  -> enforce same-video constraint
  -> enforce chronological order
  -> score event sequence
```

UI needs:

- event slots;
- timeline alignment view;
- per-event candidate frames;
- sequence score;
- chronological validity warning.

### VKIS Solver

Purpose: support video/image query in live round when the operator cannot input the query media directly.

Pipeline:

```text
operator observes query video
  -> structured memory form
  -> generated query variants
  -> hybrid search
  -> visual confirmation
```

UI needs:

- memory capture form;
- object/action/color chips;
- generated query variants;
- broad/narrow search buttons;
- fast visual result grid.

## 8. Workspace UI Model

The UI should be block-based and workspace-oriented.

Main layout:

```text
Top Command Bar
Left Query Sidebar
Main Workspace Blocks
Right Inspector
Bottom Logs / Jobs / Metrics Panel
```

### Top Command Bar

Responsibilities:

- global command palette;
- search/run command;
- mode switch: KIS, Q&A, TRAKE, VKIS, Agent;
- index/model status;
- latency indicator.

### Left Sidebar

Responsibilities:

- query/session navigation;
- query status;
- query type filtering;
- pinned candidates;
- run history;
- collections.

### Main Workspace

Responsibilities:

- show QueryBlocks;
- show RunBlocks;
- show AgentRunBlocks;
- show result grids;
- show TRAKE event alignment blocks;
- show Q&A answer panels.

### Right Inspector

Responsibilities:

- video preview;
- frame viewer;
- timeline viewer;
- OCR tab;
- ASR tab;
- caption tab;
- object/entity tab;
- metadata tab;
- evidence summary.

### Bottom Panel

Responsibilities:

- logs;
- background jobs;
- errors;
- metrics;
- system/index/model health.

### Required UI Components

Core layout:

- AppShell;
- TopBar;
- CommandPalette;
- LeftSidebar;
- MainWorkspace;
- RightInspector;
- BottomPanel;
- StatusBar.

Workspace:

- QueryBlock;
- RunBlock;
- AgentRunBlock;
- ResultGrid;
- CandidateCard;
- CandidateTray;
- CompareView;
- ParsedIntentView;
- SearchPlanView;
- EvidenceSummary.

Media:

- VideoPlayer;
- FrameViewer;
- TimelineViewer;
- ThumbnailStrip;
- ContactSheetViewer;
- ShotBoundaryOverlay;
- FrameNavigator.

Evidence:

- EvidencePanel;
- OCRPanel;
- ASRPanel;
- CaptionPanel;
- ObjectPanel;
- EntityPanel;
- ScoreBreakdown.

Query-type specific:

- KISBlock;
- QABlock;
- AnswerPanel;
- TRAKEBlock;
- EventSlot;
- TemporalAlignmentView;
- VKISMemoryForm.

System:

- JobMonitor;
- IndexStatus;
- DatasetBrowser;
- EvaluationDashboard;
- ErrorConsole;
- SettingsPanel.

## 9. Agent Model

The agent should be a bounded controller, not a free-form chatbot.

Agent loop:

```text
classify query
  -> parse constraints
  -> choose tools
  -> run retrieval
  -> fuse/rerank candidates
  -> verify evidence
  -> return candidates and trace
```

The agent must log every step. Agent output should be inspectable and replayable.

Do not let the agent directly modify core data without explicit action records. Human users should be able to inspect, override, pin, or reject agent proposals.

## 10. Evaluation and Training Loop

Evaluation is required from early development. Do not wait until the end.

Build internal benchmark sets for:

- KIS;
- Q&A;
- TRAKE;
- VKIS.

Metrics:

- KIS: Recall@10, Recall@50, Recall@100, time-to-answer;
- Q&A: retrieval accuracy, answer accuracy, end-to-end correctness;
- TRAKE: video accuracy, event accuracy, sequence accuracy, chronological validity;
- VKIS: time-to-description, time-to-answer, operator error rate;
- UI: click count, missed candidate rate, time-to-inspect;
- system: latency p50/p95, crash rate, index load time.

Error labels:

- retrieval_miss;
- rerank_wrong;
- query_parse_wrong;
- answer_wrong;
- temporal_alignment_wrong;
- operator_missed;
- ui_slow;
- system_error.

Every major retrieval/model/UI change should be evaluated against previous runs.

## 11. Roadmap

### Phase 0 — Product and Architecture Definition

Goal: define what the project is and prevent architectural drift.

Deliverables:

- ARCHITECTURE.md;
- DATA_MODEL.md;
- UI_WORKSPACE.md;
- ROADMAP.md;
- EVALUATION.md;
- P0/P1/P2 backlog.

Tasks:

- define user roles;
- define query types;
- define domain entities;
- define UI layout;
- define data lifecycle;
- define coding principles.

Exit criteria:

- domain model v1 exists;
- UI wireframe v1 exists;
- data folder convention exists;
- initial backlog exists.

### Phase 1 — Data Foundation

Goal: the system knows which videos, frames, shots, timestamps, and thumbnails exist.

Tasks:

- register dataset;
- register videos;
- import/extract frames;
- map frame to timestamp;
- generate thumbnails;
- create media asset registry;
- build basic dataset browser.

Exit criteria:

```text
open app
  -> see video list
  -> click video
  -> see frame grid
  -> click frame
  -> open correct timestamp
```

### Phase 2 — Evidence Extraction

Goal: frames/segments have searchable and inspectable evidence.

Tasks:

- define Evidence schema;
- import/generate captions;
- run/import OCR;
- run/import ASR;
- import object/concept metadata if available;
- normalize evidence text;
- link evidence to frames/time ranges;
- show evidence in inspector.

Exit criteria:

```text
click frame
  -> see caption/OCR/ASR/object evidence if available
  -> evidence has source and confidence
```

### Phase 3 — Search Baseline

Goal: query text returns candidate frames/videos with evidence.

Tasks:

- build visual embedding index;
- build text evidence index;
- implement visual search;
- implement OCR search;
- implement ASR search;
- implement caption search;
- implement hybrid fusion;
- implement candidate diversification;
- return source score breakdown.

Exit criteria:

```text
Vietnamese query
  -> top candidates
  -> thumbnail, video, frame, score, evidence
```

### Phase 4 — Workspace UI v1

Goal: make retrieval usable as a workspace tool.

Tasks:

- build app shell;
- build query sidebar;
- build query block;
- build result grid;
- build right inspector;
- build timeline viewer;
- build candidate tray;
- build bottom logs panel;
- add basic hotkeys.

Exit criteria:

```text
operator enters query
  -> sees result grid
  -> clicks candidate
  -> inspects video/timeline/evidence
  -> pins/rejects candidate
```

### Phase 5 — KIS Solver and Evaluation v0

Goal: make Textual KIS measurable and usable.

Tasks:

- implement query decomposition v0;
- extract visual/OCR/ASR/entity clues;
- implement KIS strategy;
- group by video/shot;
- create 50-100 KIS benchmark queries;
- implement Recall@K;
- label errors.

Exit criteria:

- KIS benchmark runs end-to-end;
- Recall@10/50/100 is available;
- error report exists.

### Phase 6 — Q&A Mode

Goal: retrieve evidence and answer questions.

Tasks:

- parse description vs question;
- retrieve candidates;
- inspect evidence around candidates;
- extract answer candidates;
- normalize answers;
- build AnswerPanel;
- create Q&A benchmark.

Exit criteria:

```text
Q&A query
  -> video/frame candidates
  -> answer candidates
  -> supporting evidence
```

### Phase 7 — TRAKE Mode

Goal: retrieve and align event sequences.

Tasks:

- parse event sequence;
- search candidate videos;
- search per-event frame candidates;
- enforce chronological order;
- score event sequences;
- build event slot UI;
- build timeline alignment view;
- create TRAKE benchmark.

Exit criteria:

```text
TRAKE query
  -> candidate video
  -> proposed frame for each event
  -> sequence shown on timeline
```

### Phase 8 — VKIS Mode

Goal: support live visual query from operator memory.

Tasks:

- build memory capture form;
- add object/action/color chips;
- generate query variants;
- support broad/narrow search;
- support quick visual confirmation;
- run VKIS mock practice.

Exit criteria:

```text
operator watches short clip
  -> enters structured description in 10-20 seconds
  -> system returns plausible candidates
```

### Phase 9 — Rerank, Reasoning, and Agent

Goal: improve quality and begin automation.

Tasks:

- implement rerank top-K;
- implement query expansion;
- implement evidence verifier;
- implement bounded agent;
- show agent run as block;
- support replay agent runs;
- compare baseline vs reranked metrics.

Exit criteria:

```text
agent reads query
  -> chooses search strategy
  -> runs tools
  -> reranks candidates
  -> returns candidates with trace
```

### Phase 10 — Performance and Contest Hardening

Goal: make the tool stable enough for practice and competition.

Tasks:

- profile latency;
- optimize thumbnail loading;
- virtualize result grid;
- preload indexes;
- cache recent queries;
- run heavy reranking asynchronously;
- add health checks;
- add crash recovery;
- add one-command startup;
- run mock contest sessions;
- train operator workflow.

Exit criteria:

- app survives mock contest sessions;
- search latency is acceptable;
- UI does not lag with many thumbnails;
- operator can use the tool without developer guidance.

## 12. Backlog Priority

### P0 — Required MVP

- Video/frame registry;
- thumbnail generation;
- frame/timestamp mapping;
- Evidence schema;
- OCR/caption/ASR import or generation;
- visual search baseline;
- text evidence search;
- hybrid fusion v0;
- Candidate object with evidence;
- QueryBlock UI;
- ResultGrid;
- VideoInspector;
- EvidencePanel;
- KIS solver v0;
- Evaluation set v0.

### P1 — Serious Competition Features

- Query decomposition;
- source score breakdown;
- candidate diversification;
- Q&A solver;
- AnswerPanel;
- TRAKE solver v0;
- TimelineAlignment UI;
- VKIS memory form;
- CandidateTray;
- CompareView;
- RunHistory;
- MockContest dashboard;
- hotkeys.

### P2 — Top-Team Features

- LVLM reranker;
- dense caption generation;
- advanced query expansion;
- EvidenceVerifier;
- bounded auto-agent;
- AgentRunBlock;
- advanced temporal reasoning;
- multi-user/LAN mode;
- collaboration state;
- model/index version tracking;
- ablation dashboard.

## 13. Coding Principles

### Domain-first

Code should center around domain objects, not around UI screens or model scripts.

Core objects:

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

### Evidence traceability

Every candidate must trace back to evidence. Do not return opaque scores without evidence references.

### Replayability

Every run should be replayable:

```text
same query
same config
same dataset/index/model versions
-> same or explainably similar result
```

### Config-driven behavior

Do not hardcode:

- top_k;
- fusion weights;
- index paths;
- dataset paths;
- model paths;
- rerank settings;
- thresholds.

### Interface-based retrieval

All retrieval tools should follow a consistent interface:

```text
search(request) -> candidates
```

### UI does not own business logic

UI components should render state and trigger actions. Search, reranking, solver logic, and agent control must live in core modules/services.

### Structured logs

Every run should log:

- query_id;
- run_id;
- solver;
- tools called;
- latency;
- top candidates;
- errors;
- config;
- model/index versions.

### Optimize after correctness

Do not over-optimize before the data pipeline, evidence layer, and baseline retrieval are correct. First make it correct and measurable, then make it fast.

## 14. Anti-goals

Do not build:

- a pure chatbot UI as the main interface;
- a visual-only CLIP search demo and call it complete;
- a model fine-tuning project before having evaluation;
- a UI clone of Warp without retrieval/data foundation;
- a fully autonomous agent before the retrieval tools are reliable;
- a cloud-only system that cannot run locally;
- a submission/export system as the center of the architecture;
- a collection of disconnected notebooks and scripts with no domain model.

## 15. What to Build Next

Immediate next steps:

1. Create `ARCHITECTURE.md` from this AGENT.md.
2. Create `DATA_MODEL.md` defining the domain schema.
3. Create `UI_WORKSPACE.md` defining block/panel/component layout.
4. Create repo skeleton.
5. Implement dataset/video/frame registry.
6. Implement thumbnail generation and video/frame browser.
7. Implement Evidence schema and inspector.
8. Implement baseline hybrid retrieval.
9. Implement QueryBlock + ResultGrid + Inspector UI.
10. Create the first internal KIS benchmark.

The project should move from data foundation to evidence, then retrieval, then workspace, then solvers, then evaluation, then agent, then hardening.

## 16. One-Sentence Summary

We are building a local-first, evidence-grounded multimedia retrieval workspace for AI Challenge 2026, where human operators and bounded agents can search, inspect, compare, reason over, and act on large-scale multimedia data through a fast Warp-inspired block workspace.
