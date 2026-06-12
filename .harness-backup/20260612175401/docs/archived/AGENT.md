# AGENT.md — HCMC AI Challenge 2026 Source of Truth

## 0. Purpose of This Document

This document is the working source of truth for building a competitive system for the **Ho Chi Minh City AI Challenge 2026**.

It is intended for:
- Codex agents
- engineering agents
- human developers
- AI/retrieval researchers
- product/UX contributors
- competition operators

Use this document to guide system design, implementation priorities, technical decisions, evaluation, roadmap planning, and competition strategy.

The core philosophy is:

> Build a fast, reliable, evidence-grounded **Multimedia Analysis & Retrieval Assistant**, not merely a chatbot and not merely a video search engine.

---

## 1. Competition Identity

### Official Name

**Ho Chi Minh City Artificial Intelligence Challenge 2026**  
Vietnamese: **Hội thi Thử thách Trí tuệ Nhân tạo Thành phố Hồ Chí Minh năm 2026**

### Organizer

Lead organizer:

- **Ho Chi Minh City Department of Science and Technology**  
  Vietnamese: **Sở Khoa học và Công nghệ TP.HCM**

Coordinating organizations:

- **Vietnam National University Ho Chi Minh City**  
  Vietnamese: **Đại học Quốc gia TP.HCM**
- **Ho Chi Minh City Department of Education and Training**  
  Vietnamese: **Sở Giáo dục và Đào tạo TP.HCM**
- **Ho Chi Minh Communist Youth Union of Ho Chi Minh City**  
  Vietnamese: **Thành Đoàn TP.HCM**
- **Ho Chi Minh City Computer Association**  
  Vietnamese: **Hội Tin học TP.HCM / HCA**

### Official Registration / Information Portal

`https://aichallenge.hochiminhcity.gov.vn/`

---

## 2. Competition Goals

The competition aims to:

1. Promote learning and research in computer science and artificial intelligence.
2. Encourage AI applications for the development of Ho Chi Minh City as a smart city.
3. Attract individuals and research groups from Vietnam and internationally to solve practical problems.
4. Promote creative science and technology solutions using AI.
5. Identify advanced AI solutions that can potentially be applied in Ho Chi Minh City, Vietnam, and broader regional/international contexts.

For engineering purposes, this means the system should not be treated as a toy demo. It should be designed like a practical, scalable, interactive AI system for real-world multimedia understanding and retrieval.

---

## 3. Eligibility and Competition Divisions

### Eligible Participants

The competition is open to:

- Vietnamese citizens
- Overseas Vietnamese
- Foreign nationals
- Individuals or teams

### Team Size

- Participants may register individually or as a team.
- Each team may have **no more than 5 members**.

### Divisions

#### Division A

For:

- University students
- Youth participants
- People interested in information technology and artificial intelligence

This is the primary target division for a serious technical/research team.

#### Division B

For:

- High school students interested in information technology and artificial intelligence

Important note:

- Division B participants are allowed to use tools provided by the organizers to complete competition tasks.

This likely means expectations for Division B are different from Division A. For Division A, assume teams are expected to develop their own system.

---

## 4. Official 2026 Timeline

The timeline below is based on current official information provided by the competition website/form.

| Event | Expected Time |
|---|---|
| Competition launch | May 15–20, 2026 |
| Registration period | From launch date to June 15, 2026 |
| Announcement of preliminary round content and requirements | June 25, 2026 |
| Training sessions for participants | June–July 2026 |
| Preliminary round | August 2026 |
| Preliminary round results | August 30, 2026 |
| Final round | September 12–26, 2026 |
| Award ceremony | October 2026 |

The schedule is tentative and may be adjusted by the organizers.

### Strategic Implication

There may be only around two weeks between preliminary results and the final round.

Therefore:

- Do not wait until after preliminary qualification to build the final-round UI.
- Do not wait until after preliminary qualification to practice live operation.
- Build the system and operator workflow before the preliminary round.
- Treat June–July training sessions as critical opportunities to clarify hidden rules and evaluation details.

---

## 5. Topic Evolution: 2025 vs 2026

### 2025 Topic

**Virtual assistant supports Retrieval from a large multimedia database**

Interpretation:

- A virtual assistant that supports retrieval.
- Main focus: finding relevant information from a large multimedia database.
- Strong emphasis on search/retrieval from multimedia data.

Simplified 2025 mental model:

```text
Query → Retrieval → Candidate Results
```

### 2026 Topic

**Intelligent virtual Assistant for advanced Analysis and Information retrieval from large-scale Multimedia data**

Interpretation:

- The assistant must be intelligent.
- The assistant must support advanced analysis, not only retrieval.
- The assistant must retrieve information from large-scale multimedia data.
- The system should combine multimedia understanding, retrieval, reasoning, and evidence-grounded answering.

Simplified 2026 mental model:

```text
Query
→ Intent Understanding
→ Multimedia Evidence Retrieval
→ Advanced Analysis
→ Reasoning / Synthesis
→ Answer / Segment / Evidence
```

### Key Strategic Difference

2025 was primarily about:

> Find the right item from a large multimedia database.

2026 is about:

> Find the right evidence, analyze it, and return useful information or answers grounded in multimedia data.

Therefore, the 2026 system should be designed as a:

> **Multimedia Analysis & Retrieval Assistant**

not just a:

> Multimedia Retrieval Assistant

---

## 6. Official 2026 Problem Statement

Participants must develop:

> An intelligent virtual assistant that supports advanced analysis and information retrieval from large-scale multimedia data, including images, audio, and text.

The competition format is similar to international challenges such as:

- **Lifelog Search Challenge (LSC)**
- **Video Browser Showdown (VBS)**

The competition encourages participants to develop and integrate solutions for:

- large-scale data processing
- Vietnamese-specific data processing
- language understanding
- audio understanding
- image/video understanding
- Large Vision Language Models
- generative AI
- intelligent interaction between modules/systems

---

## 7. Competition Modes

The 2026 competition is expected to move toward two competition modes.

## 7.1 Traditional Mode

In traditional mode:

> A human user uses the team's intelligent virtual assistant tool to process information retrieval queries from a multimedia database.

This is a human-in-the-loop interactive retrieval mode.

### Engineering Implications

The system needs:

- fast UI
- low-latency search
- useful candidate previews
- video timeline navigation
- keyboard-first workflow
- rapid filtering
- evidence display
- query history
- candidate comparison
- reliable submission/export flow

In this mode, the human operator is part of the system.

A strong model with a poor UI may lose to a weaker model with a better interaction workflow.

## 7.2 Automatic Mode

In automatic mode:

> The competition will experiment with automatic competition between intelligent virtual assistants from different teams.

This means the system may need to process queries automatically without manual human intervention.

### Engineering Implications

The system needs:

- query understanding
- query decomposition
- modality routing
- retrieval planning
- automatic search execution
- reranking
- answer verification
- confidence scoring
- fallback logic
- bounded retry/refinement loops

The automatic system should not be an unconstrained chatbot. It should be a bounded agent with deterministic, inspectable behavior.

---

## 8. First-Principles Product Interpretation

Start from the real user need:

> Given a very large multimedia collection, the user wants to quickly find or understand information that may be distributed across video, image, speech, text, OCR, metadata, and temporal context.

Therefore, the product must solve four fundamental jobs:

1. **Find**
   - Retrieve relevant frames, shots, videos, segments, transcripts, or text evidence.

2. **Understand**
   - Interpret what is visible, spoken, written, or implied in multimedia data.

3. **Analyze**
   - Compare, summarize, reason across time, combine modalities, and answer questions.

4. **Act**
   - Return the correct video/frame/timestamp/answer quickly and reliably in the required competition format.

The winning system is likely not the one with the largest model. It is likely the one that produces the correct answer fastest and most reliably under competition constraints.

---

## 9. Core Product Principle

### Do Not Start With a Chatbot

A chatbot alone is not enough.

The assistant must be grounded in a strong retrieval and evidence system.

Recommended build order:

```text
1. Multimedia Retrieval Core
2. Evidence Extraction Layer
3. Analysis / QA Layer
4. Human-in-the-loop UI
5. Automatic Agent Mode
6. Competition Workflow and Evaluation
```

### Correct Product Mental Model

```text
Fast hybrid retrieval
+ strong evidence extraction
+ Vietnamese-aware query understanding
+ good UI for human operation
+ bounded auto-agent
+ rigorous evaluation
= competitive AI Challenge system
```

---

## 10. Expected Query Types

The exact 2026 query set is not yet fully known, but based on official references to LSC/VBS and multimedia assistant requirements, the system should prepare for the following query types.

## 10.1 Textual Known-Item Search

Example:

> Find the scene where a man in a red shirt stands next to a bus.

Requires:

- text-to-visual retrieval
- object/action/scene understanding
- caption search
- visual reranking
- timestamp localization

## 10.2 Visual Known-Item Search

The organizer may show an image or video clip and ask teams to find the corresponding item in the database.

Requires:

- image/video similarity search
- visual embedding retrieval
- near-duplicate search
- frame/shot localization

If direct image input is not allowed, the operator must quickly convert the visual clue into text constraints.

## 10.3 Question Answering Over Multimedia

Example:

> What is the main topic discussed in the segment where the speaker is standing in front of a blue screen?

Requires:

- retrieval
- ASR/transcript search
- OCR search
- visual context
- evidence selection
- answer synthesis

## 10.4 OCR-Based Search

Example:

> Find the scene containing the text "Ủy ban nhân dân".

Requires:

- OCR extraction
- fuzzy text search
- Vietnamese text normalization
- visual preview for verification

## 10.5 Audio / Speech-Based Search

Example:

> Find the segment where someone talks about digital transformation in education.

Requires:

- ASR
- transcript segmentation
- Vietnamese speech recognition
- transcript search
- mapping transcript segments back to video timestamps

## 10.6 Temporal Reasoning Queries

Example:

> Find what happens after the person enters the building.

Requires:

- timeline navigation
- neighboring segment retrieval
- temporal expansion
- event sequence reasoning

## 10.7 Hybrid Reasoning Queries

Example:

> Find a segment where a speaker discusses AI while a slide about smart cities is visible.

Requires:

- ASR for "AI"
- OCR for slide text
- visual detection for speaker/stage/screen
- fusion and evidence verification

## 10.8 Ambiguous Natural-Language Queries

Example:

> Find a scene that looks like a product launch event.

Requires:

- query expansion
- semantic retrieval
- scene understanding
- diversity-aware candidate ranking

---

## 11. High-Level System Architecture

Recommended architecture:

```text
                      ┌─────────────────────┐
                      │ User / Judge Query   │
                      └──────────┬──────────┘
                                 │
                                 v
                      ┌─────────────────────┐
                      │ Query Understanding  │
                      │ - intent             │
                      │ - entities           │
                      │ - constraints        │
                      │ - modality routing   │
                      └──────────┬──────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
              v                  v                  v
     ┌────────────────┐ ┌────────────────┐ ┌────────────────┐
     │ Human UI        │ │ Auto Agent      │ │ Batch Pipeline  │
     └────────┬───────┘ └────────┬───────┘ └────────┬───────┘
              │                  │                  │
              └──────────────────┼──────────────────┘
                                 v
                      ┌─────────────────────┐
                      │ Retrieval Core API   │
                      └──────────┬──────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
        v                        v                        v
┌────────────────┐      ┌────────────────┐      ┌────────────────┐
│ Visual Index    │      │ Text/OCR Index │      │ ASR Index       │
│ CLIP/SigLIP     │      │ BM25/Embedding │      │ Transcript      │
└────────┬───────┘      └────────┬───────┘      └────────┬───────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 v
                      ┌─────────────────────┐
                      │ Fusion + Reranking   │
                      └──────────┬──────────┘
                                 │
                                 v
                      ┌─────────────────────┐
                      │ Evidence / Answer    │
                      │ - video_id           │
                      │ - timestamp          │
                      │ - frame_id           │
                      │ - answer text        │
                      │ - confidence         │
                      └─────────────────────┘
```

---

## 12. Required System Layers

## 12.1 Data Ingestion Layer

Responsibilities:

- load videos
- load provided metadata
- extract keyframes if needed
- generate thumbnails
- normalize timestamps
- create shot/segment records
- validate file paths
- detect duplicates
- prepare data for indexing

The ingestion pipeline must be repeatable.

Required features:

- full rebuild
- incremental rebuild
- validation mode
- sample viewer
- checksum or consistency checks

## 12.2 Evidence Extraction Layer

Responsibilities:

- visual embeddings
- object/concept extraction
- image/video captioning
- OCR extraction
- ASR transcription
- metadata normalization
- optional scene/event labels

This layer converts raw multimedia into searchable evidence.

## 12.3 Retrieval Layer

Responsibilities:

- visual similarity search
- text/caption search
- OCR search
- ASR search
- metadata filtering
- temporal retrieval
- hybrid fusion

## 12.4 Analysis Layer

Responsibilities:

- query decomposition
- evidence aggregation
- reasoning across modalities
- temporal reasoning
- answer generation
- confidence estimation
- top-K verification

## 12.5 UI Layer

Responsibilities:

- search interaction
- candidate browsing
- video preview
- timeline navigation
- result comparison
- fast submission/copy/export
- operator workflow

## 12.6 Auto-Agent Layer

Responsibilities:

- parse query
- choose strategy
- call tools
- fuse results
- verify top candidates
- decide whether to answer, refine, or fallback

## 12.7 Evaluation Layer

Responsibilities:

- benchmark set
- Recall@K
- time-to-answer
- latency
- failure analysis
- query-type breakdown
- human vs auto comparison

---

## 13. Recommended Data Schema

Use a normalized schema that supports frame-level, segment-level, and video-level retrieval.

Example logical schema:

```json
{
  "video_id": "video_001",
  "segment_id": "video_001_seg_000123",
  "shot_id": "video_001_shot_000045",
  "frame_id": "video_001_frame_000123",
  "timestamp": 123.45,
  "frame_path": "data/frames/video_001/000123.jpg",
  "thumbnail_path": "data/thumbs/video_001/000123.jpg",
  "source_video_path": "data/videos/video_001.mp4",
  "caption": "A person is speaking in front of a large screen.",
  "objects": ["person", "microphone", "screen"],
  "ocr_text": "HỘI NGHỊ CHUYỂN ĐỔI SỐ",
  "asr_text": "hôm nay chúng ta nói về chuyển đổi số trong giáo dục",
  "visual_embedding_id": "emb_visual_000123",
  "text_embedding_id": "emb_text_000123",
  "duration": 600.0,
  "fps": 25,
  "metadata": {
    "source": "provided_or_extracted",
    "language": "vi",
    "quality_flags": []
  }
}
```

Important:

- Keep raw data separate from derived data.
- Every derived artifact should be traceable to source video/time/frame.
- All results must map back to competition submission identifiers.

---

## 14. Retrieval Strategy

Use hybrid retrieval. Do not depend on one modality.

## 14.1 Visual Retrieval

Use for:

- objects
- scenes
- actions
- colors
- visual similarity
- visual known-item search

Possible models:

- CLIP
- SigLIP
- EVA-CLIP
- organizer-provided embeddings if available

Possible index:

- FAISS
- Qdrant
- Milvus

Local FAISS is recommended for speed and simplicity unless distributed serving is required.

## 14.2 Caption Retrieval

Use for:

- semantic event descriptions
- scene understanding
- actions
- richer search than raw object labels

Caption generation may use:

- Qwen2.5-VL
- InternVL
- LLaVA-family
- BLIP/BLIP-2
- other LVLMs allowed by competition rules

Captions should include:

- visible people
- actions
- objects
- scene/context
- colors if important
- visible text if obvious
- relationships between objects
- event type

## 14.3 OCR Retrieval

Use for:

- signs
- banners
- slides
- names
- organizations
- locations
- product names
- labels

Possible tools:

- PaddleOCR
- VietOCR
- EasyOCR

Vietnamese normalization is important:

- lowercasing
- accent handling
- whitespace normalization
- punctuation removal
- fuzzy matching
- possible accent-insensitive search

## 14.4 ASR Retrieval

Use for:

- speech content
- interviews
- presentations
- news reports
- named entities spoken in audio
- topic search

Possible tools:

- Whisper large-v3
- Whisper turbo
- Vietnamese ASR models if available and better
- organizer-provided transcripts if available

Important:

- Segment transcripts by timestamp.
- Map transcript chunks back to video time ranges.
- Use both exact keyword search and semantic search.

## 14.5 Metadata Retrieval

Use organizer-provided metadata whenever available:

- keyframes
- embeddings
- object concepts
- descriptions
- transcripts
- video descriptions
- other provided features

Do not reprocess everything blindly if the organizers already provide high-quality metadata.

## 14.6 Temporal Retrieval

Use for:

- before/after queries
- adjacent event search
- finding exact timestamp after approximate retrieval
- expanding around a candidate

Support operations:

- get frames around timestamp ±5s, ±10s, ±30s
- show previous/next shots
- jump to nearest transcript segment
- jump to nearby OCR hit
- search similar frames around candidate

---

## 15. Fusion and Reranking

Do not simply concatenate results from different indexes. Use score fusion and reranking.

Example dynamic fusion:

```text
final_score =
  w_visual  * visual_score
+ w_caption * caption_score
+ w_asr     * asr_score
+ w_ocr     * ocr_score
+ w_object  * object_score
+ w_meta    * metadata_score
```

Weights should depend on query type.

Example weights:

| Query Type | Visual | Caption | ASR | OCR | Object/Meta |
|---|---:|---:|---:|---:|---:|
| Visual scene | 0.45 | 0.25 | 0.05 | 0.05 | 0.20 |
| Spoken content | 0.15 | 0.20 | 0.50 | 0.05 | 0.10 |
| Text on screen | 0.10 | 0.15 | 0.05 | 0.60 | 0.10 |
| Hybrid event | 0.30 | 0.30 | 0.20 | 0.10 | 0.10 |
| Temporal query | 0.25 | 0.25 | 0.20 | 0.05 | 0.25 |

Reranking options:

- cross-encoder reranker
- text embedding reranker
- LVLM verification over top candidates
- rule-based constraint matching
- temporal consistency checks
- diversity-aware ranking

Important principle:

> Use expensive models only on top-K candidates, not on the entire dataset.

---

## 16. Query Understanding

The query understanding layer should convert natural-language input into structured constraints.

Example output:

```json
{
  "query_type": "hybrid_event_search",
  "intent": "find_video_segment",
  "visual_constraints": {
    "objects": ["person", "microphone", "screen"],
    "actions": ["speaking", "presenting"],
    "scene": ["conference", "stage"],
    "colors": ["blue"]
  },
  "audio_constraints": {
    "keywords": ["chuyển đổi số", "giáo dục"],
    "semantic_topics": ["digital transformation", "education"]
  },
  "ocr_constraints": {
    "keywords": ["AI", "TP.HCM", "hội nghị"]
  },
  "temporal_constraints": {
    "before": null,
    "after": null,
    "near": null
  },
  "search_strategy": ["asr", "caption", "visual", "ocr"],
  "expected_output": "video_id_timestamp"
}
```

Use query understanding for:

- modality routing
- dynamic fusion weights
- query expansion
- auto-agent planning
- UI hints

---

## 17. Vietnamese-Specific Requirements

The competition explicitly encourages handling data specific to Vietnam, including language, audio, and images.

Therefore, the system should support:

### Vietnamese Text

- Vietnamese tokenization if useful
- accent-preserving search
- accent-insensitive search
- synonym expansion
- bilingual Vietnamese-English query expansion
- named entity handling

Examples:

```text
xe máy → motorbike, motorcycle, scooter
ô tô → car, automobile
phát biểu → speech, speaking, presentation
hội nghị → conference, seminar
chuyển đổi số → digital transformation
trí tuệ nhân tạo → artificial intelligence, AI
```

### Vietnamese Speech

- Vietnamese ASR quality matters.
- Background noise may be present.
- News and presentation audio may include formal Vietnamese.
- Named entities may be misrecognized and need fuzzy matching.

### Vietnamese Visual Context

The model may need to recognize:

- Vietnamese signs
- official banners
- local places
- local public-service contexts
- government/education/urban scenes
- Vietnamese street and social environments

---

## 18. Human UI Requirements

The traditional mode requires an excellent operator UI.

### Essential UI Features

- query input
- search mode selector or auto mode
- thumbnail grid
- large image preview
- video preview around timestamp
- timeline navigation
- candidate score display
- evidence panel
- OCR evidence
- ASR evidence
- caption evidence
- object/concept evidence
- query history
- candidate tray
- copy/export/submit result

### Keyboard Shortcuts

Recommended:

| Key | Action |
|---|---|
| Enter | Run search |
| 1–9 | Open candidate |
| S | Submit/copy selected candidate |
| F | Find visually similar candidates |
| [ / ] | Move backward/forward in time |
| A | Toggle ASR evidence |
| O | Toggle OCR evidence |
| C | Toggle caption evidence |
| V | Open video preview |
| Esc | Close preview |

### UI Product Principle

The UI should minimize:

- reading time
- click count
- visual scanning effort
- accidental submissions
- operator confusion

A good target:

- easy queries: answer in 10–20 seconds
- medium queries: answer in 30–60 seconds
- hard queries: preserve candidates and refine quickly

---

## 19. Auto-Agent Requirements

The auto-agent should be bounded, inspectable, and tool-driven.

Recommended loop:

```text
1. Receive query
2. Classify query type
3. Extract constraints
4. Generate search plans
5. Run retrieval tools in parallel
6. Fuse candidates
7. Rerank top-K
8. Verify top candidates
9. Estimate confidence
10. Return answer or refine once/twice
```

Do not allow unlimited loops.

### Search Plan Example

```json
{
  "query": "Find the segment where a speaker discusses digital transformation in education in front of a blue screen.",
  "query_type": "hybrid",
  "plans": [
    {
      "tool": "asr_search",
      "query": "chuyển đổi số giáo dục digital transformation education",
      "top_k": 100
    },
    {
      "tool": "visual_search",
      "query": "speaker presenting in front of blue screen",
      "top_k": 100
    },
    {
      "tool": "caption_search",
      "query": "conference speaker presentation blue screen education technology",
      "top_k": 100
    },
    {
      "tool": "ocr_search",
      "query": "giáo dục chuyển đổi số AI",
      "top_k": 50
    }
  ],
  "fusion_policy": "hybrid_event",
  "rerank_policy": "prefer candidates supported by both ASR and visual evidence"
}
```

### Confidence Policy

High confidence when:

- multiple modalities agree
- top-1 is clearly separated from top-2
- evidence matches query constraints
- timestamp is consistent with transcript/visual context
- LVLM or reranker verifies the candidate

Low confidence when:

- only one weak modality matches
- top candidates are very close
- evidence is incomplete
- OCR/ASR is noisy
- query is ambiguous

Low-confidence behavior:

- return top-N candidates
- refine query once or twice
- avoid reckless auto-submission if rules penalize wrong answers

---

## 20. Evaluation Strategy

Build an internal evaluation benchmark before official data is released.

### Metrics

Use both retrieval and competition metrics.

#### Retrieval Metrics

- Recall@1
- Recall@5
- Recall@10
- Recall@50
- Mean Reciprocal Rank
- top-K contains correct video
- top-K contains correct timestamp range

#### Product Metrics

- median query latency
- p95 query latency
- time-to-answer
- number of clicks per answer
- number of query refinements
- number of wrong submissions
- operator miss rate
- crash rate

#### Auto-Agent Metrics

- success rate by query type
- confidence calibration
- average tool calls per query
- average latency
- refinement success rate
- hallucination/wrong-answer rate

### Suggested Readiness Targets

| Metric | Minimum Competitive | Strong Competitive |
|---|---:|---:|
| Recall@50 for common query types | >70% | >85% |
| Median search latency | <2s | <1s |
| Easy query time-to-answer | <45s | <20s |
| Medium query time-to-answer | <90s | <45s |
| UI crash rate in mock contests | 0 | 0 |
| Correct result in top-100 but missed by operator | <20% | <5% |
| Auto-agent success on easy queries | >50% | >70% |

---

## 21. Mock Contest Practice

Mock contests are mandatory.

### Mock Contest Format

- 30–50 queries per session
- strict time limits
- no pausing to fix code
- one person acts as judge/query giver
- record screen if possible
- track submissions and mistakes
- review after session

### Error Taxonomy

Classify every failure:

| Failure Type | Meaning | Fix |
|---|---|---|
| Retrieval failure | correct item not in top-K | improve index, captions, ASR/OCR, fusion |
| Ranking failure | correct item exists but ranked too low | improve reranking |
| UI failure | correct item visible but not noticed | improve UI layout/preview |
| Operator failure | user chose wrong result | training, better evidence display |
| Timestamp failure | right video, wrong moment | improve temporal expansion |
| Query understanding failure | system searched wrong concepts | improve parser/expansion |
| Latency failure | system too slow | optimize index/cache/API |
| Agent failure | auto-agent chose wrong plan | improve planning/confidence |

---

## 22. Roadmap

## Phase 1 — Before Registration Deadline

Goal:

> Build an ugly but working baseline.

Tasks:

- finalize team
- create repo
- create mini dataset
- implement ingestion
- extract keyframes
- generate thumbnails
- build visual index
- build text/OCR/ASR indexes
- implement hybrid search API
- create simple UI
- create 100 internal queries
- measure Recall@K

Deliverable:

```text
Vietnamese query → top frames/videos/timestamps → preview works
```

## Phase 2 — June 25 to End of July

Goal:

> Adapt to official preliminary requirements and training information.

Tasks:

- read official preliminary requirements
- attend training sessions
- ask rule clarification questions
- ingest official dataset if released
- map official requirements to existing modules
- close technical gaps
- tune fusion/reranking
- run weekly mock contests

Deliverable:

```text
System compatible with official preliminary format
```

## Phase 3 — August Preliminary Round

Goal:

> Qualify reliably.

Tasks:

- freeze stable version
- validate submission/export format
- avoid risky late changes
- run batch retrieval
- log outputs
- review candidates if allowed
- keep backup indexes and environment

Deliverable:

```text
Reproducible preliminary submission
```

## Phase 4 — After Preliminary Results to Final Round

Goal:

> Maximize live competition performance.

Tasks:

- assign operator roles
- run mock contests frequently
- optimize UI based on observed mistakes
- improve hotkeys and timeline navigation
- improve similar-frame search
- optimize latency
- finalize auto-agent mode
- freeze competition build

Deliverable:

```text
Stable final-round system + trained team workflow
```

---

## 23. Suggested Team Roles

Maximum team size: 5.

Recommended roles:

| Role | Responsibilities |
|---|---|
| Technical Lead / Architect | system architecture, tradeoff decisions, integration, final technical quality |
| AI Retrieval Engineer | embeddings, indexes, reranking, evaluation |
| Backend/Data Engineer | ingestion, APIs, storage, performance, reproducibility |
| Frontend/UX Engineer | search console, video preview, hotkeys, operator workflow |
| Agent/QA/Operator Lead | auto-agent, query set, mock contests, error analysis |

If the team has fewer people, combine roles but preserve responsibilities.

Most important skills to cover:

1. retrieval/backend
2. frontend/operator UI
3. data pipeline
4. evaluation
5. agent/reasoning

---

## 24. Recommended Tech Stack

### Backend

- Python
- FastAPI
- FAISS
- DuckDB or PostgreSQL
- Elasticsearch/OpenSearch/Tantivy for text search
- Redis for caching
- Celery/RQ for offline processing
- Docker Compose

### AI / ML

- CLIP / SigLIP / EVA-CLIP for visual embeddings
- organizer-provided embeddings if available
- bge-m3 / multilingual-e5 / Jina multilingual embeddings for text
- PaddleOCR / VietOCR / EasyOCR for OCR
- Whisper large-v3 / Whisper turbo / Vietnamese ASR models for speech
- Qwen2.5-VL / InternVL / LLaVA-family / BLIP-family for captioning and LVLM verification
- bge-reranker or cross-encoder reranker for top-K reranking

### Frontend

- Next.js or React
- HTML5 video player
- thumbnail grid
- keyboard shortcuts
- video timeline viewer
- evidence panel

### Infrastructure

- Docker Compose for local reproducibility
- local NVMe storage for indexes/thumbnails if possible
- GPU machine for preprocessing if available
- CPU-compatible search runtime for robustness
- one-command startup script

---

## 25. Product Backlog

## P0 — Must Have

- data ingestion pipeline
- frame/segment schema
- thumbnail generation
- visual search
- text/caption search
- OCR search
- ASR or transcript search
- hybrid fusion
- search API
- simple UI
- video preview
- result export/submission helper
- logging
- internal evaluation set

## P1 — Should Have

- dynamic query parser
- query expansion
- reranker
- timeline expansion
- similar-frame search
- candidate tray
- hotkeys
- evidence panel
- auto-agent v0
- mock contest dashboard

## P2 — Nice to Have

- collaborative multi-operator UI
- advanced LVLM verification
- automatic ablation reporting
- multi-GPU preprocessing
- sophisticated temporal reasoning
- paper-ready experiment tracking
- advanced analytics dashboard

---

## 26. Questions to Ask Organizers During Training

Ask these questions as early as possible.

### Dataset

1. What data will be provided?
2. Will videos, keyframes, metadata, embeddings, transcripts, OCR, or captions be provided?
3. Are teams allowed to extract additional features?
4. Are teams allowed to use external datasets?
5. Are teams allowed to use pretrained models?
6. Are teams allowed to use commercial APIs?

### Runtime

7. Will final-round systems run locally, on team servers, or in an organizer environment?
8. Will internet access be available?
9. Are cloud services allowed?
10. Are there hardware limits?
11. Are GPUs allowed during final round?
12. Is preprocessing allowed before the live round?

### Task Format

13. What query types will appear?
14. Will queries be text-only, image-based, video-based, audio-based, or mixed?
15. Will queries be in Vietnamese, English, or both?
16. Will there be Q&A tasks?
17. Will there be temporal reasoning tasks?
18. Will there be automatic mode in 2026 final scoring or only experimental demonstration?

### Scoring

19. What is the official submission format?
20. Is the answer a video ID, frame ID, timestamp, text answer, or combination?
21. Is wrong submission penalized?
22. Are multiple submissions allowed?
23. How is time scored?
24. Are explanations/evidence required?
25. Are UI/solution quality judged separately from retrieval score?

### Compliance

26. Are there restrictions on generative AI?
27. Are there restrictions on LVLMs?
28. Are there restrictions on model size?
29. Are there data privacy or licensing constraints?
30. Are teams required to disclose methods?

---

## 27. Competition Strategy

## 27.1 Preliminary Round Strategy

Primary goal:

> Qualify safely.

Do:

- prioritize stability
- follow output format exactly
- use batch scripts
- log all candidates
- validate submissions
- avoid last-minute risky changes
- use human review if allowed

Do not:

- rely only on an experimental agent
- change schema at the last minute
- submit without validation
- optimize for elegance over correctness

## 27.2 Final Round Strategy

Primary goal:

> Answer correctly and quickly under pressure.

Do:

- train operators
- use hotkeys
- keep UI simple and fast
- display evidence clearly
- use candidate trays
- search multiple modalities
- use temporal expansion
- submit confidently

Do not:

- overtrust top-1 result
- ignore ASR/OCR evidence
- waste time on perfect reasoning when a visual match is enough
- let the agent perform unlimited retries
- depend on unstable internet/API unless allowed and tested

---

## 28. Research / Paper Strategy

The official benefits mention that high-performing teams may be invited to present at a Special Session on Lifelog and Multimedia Event Retrieval at SoICT 2026, with proceedings published by ACM. Some methods may also be considered for a Special Issue in Multimedia Tools and Applications.

Therefore, build the project so that it can become a research contribution.

Log:

- architecture
- dataset statistics
- query types
- baselines
- proposed methods
- ablations
- latency
- Recall@K
- human vs auto mode performance
- error analysis
- screenshots
- agent traces
- case studies

Possible research framing:

> Vietnamese-aware multimodal assistant for large-scale multimedia analysis and retrieval, combining visual-language retrieval, ASR/OCR-grounded evidence, bounded agentic query planning, and human-in-the-loop interaction.

Avoid framing the work as merely:

> We used CLIP + FAISS.

A stronger contribution is:

> We designed and evaluated a practical multimodal analysis and retrieval assistant optimized for Vietnamese large-scale multimedia search in both human-in-the-loop and automatic challenge settings.

---

## 29. Anti-Patterns to Avoid

Do not:

1. Start by building only a chatbot.
2. Spend most of the time fine-tuning models before having an end-to-end system.
3. Build a beautiful UI that is slow.
4. Build a fast backend without a usable operator UI.
5. Ignore OCR and ASR.
6. Ignore Vietnamese query expansion and normalization.
7. Depend entirely on one embedding model.
8. Skip internal evaluation.
9. Skip mock contests.
10. Let the auto-agent behave non-deterministically without logs.
11. Make late-stage breaking changes before the preliminary round.
12. Assume the final round is only about model quality.
13. Ignore submission/export format.
14. Fail to map every result back to official IDs/timestamps.
15. Wait for the official dataset before building the baseline.

---

## 30. Engineering Rules for Codex Agents

When modifying this codebase, agents should follow these rules.

### Product Rules

1. Prioritize end-to-end working behavior over isolated model experiments.
2. Every feature must support either retrieval quality, analysis quality, operator speed, auto-agent reliability, or evaluation.
3. Avoid adding complex dependencies unless they clearly improve competition performance.
4. Prefer simple, inspectable pipelines over opaque cleverness.
5. Build for repeatability and debugging.

### Data Rules

1. Every frame/segment must map back to source video and timestamp.
2. Never lose official IDs.
3. Derived artifacts must be reproducible from raw/provided data.
4. Keep raw data immutable.
5. Validate indexes after building.

### API Rules

1. Retrieval APIs should be usable by both UI and auto-agent.
2. APIs should return evidence, not only scores.
3. Include video_id, frame_id, timestamp, modality, score, and evidence fields.
4. Support top_k parameter.
5. Support filtering and temporal expansion where possible.

Example result object:

```json
{
  "video_id": "video_001",
  "frame_id": "video_001_frame_000123",
  "timestamp": 123.45,
  "score": 0.873,
  "modalities": ["visual", "asr", "ocr"],
  "evidence": {
    "caption": "A speaker is presenting in front of a blue screen.",
    "asr": "chuyển đổi số trong giáo dục",
    "ocr": "AI FOR SMART CITY"
  }
}
```

### UI Rules

1. Optimize for speed, not decoration.
2. Reduce clicks.
3. Support keyboard shortcuts.
4. Show evidence near each candidate.
5. Make timestamps easy to verify.
6. Keep candidate comparison simple.

### Agent Rules

1. Use bounded loops.
2. Log every decision.
3. Use structured query plans.
4. Prefer tool calls over free-form reasoning.
5. Estimate confidence.
6. Return top candidates when uncertain.
7. Avoid hallucinating evidence.

### Evaluation Rules

1. Every major retrieval change must be evaluated.
2. Track metrics by query type.
3. Record latency.
4. Keep failure examples.
5. Do not rely only on subjective inspection.

---

## 31. Minimum Viable System Definition

The minimum viable competition system is:

```text
A system that can ingest a multimedia dataset,
extract or load searchable evidence,
build visual/text/OCR/ASR indexes,
accept Vietnamese natural-language queries,
return ranked video/frame/timestamp candidates,
show evidence in a fast UI,
preview video around candidate timestamps,
and export/submit results in the required format.
```

This is the baseline.

The competitive version adds:

```text
dynamic query understanding,
query expansion,
fusion/reranking,
temporal reasoning,
automatic agent mode,
mock contest optimization,
and research-grade logging.
```

---

## 32. Current Strategic Conclusion

Based on all known information, the best strategy for AI Challenge 2026 is:

```text
Build a robust multimedia retrieval engine first.
Add evidence extraction and advanced analysis.
Expose it through a fast human-in-the-loop UI.
Wrap it with a bounded automatic agent.
Train with mock contests.
Log everything for improvement and research.
```

The system should be optimized for:

1. Correctness
2. Speed
3. Evidence grounding
4. Operator usability
5. Automatic reliability
6. Reproducibility
7. Research value

The winning mindset:

> This is not a model contest.  
> This is a productized AI system contest under research-challenge constraints.
