# Retrieval Workflows & Automatic Agent

## Status

Canonical Specification for Retrieval Workflows and Agent boundaries. Derived from `SPEC.md`.

---

## 1. Retrieval Query Workflows

The engine must support four primary query workflows defined by the AI Challenge theme.

### Textual KIS (TKIS)
- **Goal**: Find a specific keyframe based on a detailed text clue.
- **Flow**: Text input -> Hybrid FAISS visual search + FTS5 text search (captions/OCR) -> Sorted result grid.

### Q&A (Visual Question Answering)
- **Goal**: Identify the exact frame that answers a visual question and extract the text/fact answer.
- **Flow**: Query -> FTS5 object count filter + visual similarity -> Detail view -> Edit answer box -> Save card.

### TRAKE (Temporal Relationship)
- **Goal**: Find an ordered sequence of events or actions in one video.
- **Flow**: Multiple clues -> Temporal search -> Browse same-video keyframes chronologically -> Select start/end sequence -> Save TRAKE rows.

### VKIS (Video KIS)
- **Goal**: Find the matching video file and sequence from raw clips.
- **Flow**: Group ranked frames by video -> Video Explorer -> Inspect timeline.

---

## 2. Automatic Agent Mode

The system must support an automated search and reasoning agent alongside the human interface.

### Principles:
1. **Shared Core**: The agent runs on top of the exact same FastAPI services, database, indexes, and media tools as the Web UI. No separate agent-only database or search path is allowed.
2. **Command Pattern**: Agent calls must be structured, traceable, and recordable tool calls:
   ```json
   {
       "tool": "search_hybrid",
       "arguments": {"query": "traffic jam", "mode": "hybrid", "weights": {"visual": 0.7, "text": 0.3}}
   }
   ```
3. **Execution Logging**: Every tool call, intermediate score, and LLM reasoning step must be persisted to the runtime SQLite `agent_runs` table.
4. **UI Integration**: Teammates must be able to view, accept, reject, or edit candidates found by the agent directly inside the shared Web UI.
