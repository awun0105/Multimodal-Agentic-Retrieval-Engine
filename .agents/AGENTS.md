# [CRITICAL INITIALIZATION PROTOCOL]
At the beginning of EVERY new conversation, before taking any action or generating any code, you MUST use the iew_file or un_command tool to read the following context files to understand the project architecture, progress, and user rules:
1. .agents/context/project_structure_and_progress.md (Project Architecture and Status)
2. .agents/rules/user_rules.md (Strict User Rules)
3. .agents/notes/handover_log.md (If exists, read the latest handover instructions)

You must silently acknowledge that you have read these files in your first thought process. Do NOT ask for permission to read them, just read them immediately.

---
# Agent Workspace Guidelines & Operating Rules

## Project Scope & Canonical Location
- Root Workspace: `c:\Nhat_Code\aio\project\AIC\Multimodal-Agentic-Retrieval-Engine`
- Core Repository: `Multimodal-Agentic-Retrieval-Engine`
- Active Branch: `dev`

## Partner-Style Vibe Coding & Architectural Discussion Rules
1. **High-Level Architectural & Conceptual Discussion**:
   - Focus on model architecture, system design, data flow, component interactions, and structural trade-offs.
   - Omit heavy mathematical formulas and detailed calculations. Keep discussions focused on high-level intuition, structural mechanisms, and practical design choices.
   - Exchange research ideas, model options, and architectural strategies before writing code.
2. **Mandatory Empirical Verification & Evidence**:
   - Every completed step must be backed by empirical evidence (terminal output, execution logs, benchmark stats, test metrics, data samples).
3. **Canonical Data Contracts (Dev Branch)**:
   - Source of Truth: Canonical docs in `Multimodal-Agentic-Retrieval-Engine/docs/`.
   - References: `video_ref`, `keyframe_ref`, `thumbnail_ref`.
   - Model: `google/siglip-base-patch16-224` (SigLIP Base). Output index: `siglip.faiss` linked via `vector_map` & `embeddings_meta` in SQLite.
4. **Tone & Formatting Constraints**:
   - Strictly NO emojis/icons anywhere (in source code, docstrings, comments, notebook markdown cells, execution logs, documentation, or chat responses).
   - Use clean, simple, and professional technical language.

