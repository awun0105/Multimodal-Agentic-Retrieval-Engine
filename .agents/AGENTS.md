# Agent Workspace Guidelines & Operating Rules

## Project Scope & Canonical Location
- Root Repository: `Multimodal-Agentic-Retrieval-Engine`
- Active Branch: `dev`
- Domain: HCMC AI Challenge (AIC 2026) - Multimodal Video Retrieval Engine

## Architectural Focus & Empirical Verification
1. **High-Level Architectural Discussion**:
   - Focus strictly on model architecture, component design, pipeline flow, and structural choices.
   - Omit heavy mathematical formulas and detailed calculations. Keep discussions clear, architectural, and concept-driven.
2. **Step-by-Step Empirical Verification & Proof**:
   - Never declare a step done without concrete empirical proof.
   - After completing any step, present empirical evidence: test execution outputs, logs, benchmark metrics, output data samples, or visual proofs.
3. **Core Data Contracts (Dev Branch Alignment)**:
   - Source of Truth: Refer to canonical documentation in `docs/README_CANONICAL_MAP.md` and `docs/architecture/data-contracts.md`.
   - Canonical Logical References: `video_ref`, `keyframe_ref`, `thumbnail_ref`.
   - Default Embedding Model: `google/siglip-base-patch16-224` (SigLIP Base). Output index: `siglip.faiss` linked via `vector_map` and `embeddings_meta` in SQLite.
