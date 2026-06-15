# Phase 6 — Retrieval Foundations

## Maps To

- `MVP-4`
- `MVP-5`
- `SYS2-003`
- `SYS2-004`

## Goal

Đưa retrieval thật vào System 2 trên app-ready artifacts đã có:

- visual retrieval bằng FAISS
- text retrieval bằng FTS5

## Scope

- FAISS runtime adapter
- FTS5 runtime adapter
- search endpoints
- evidence-aware ranked results

## Suggested Issue Breakdown

1. Implement FAISS adapter
2. Resolve `vector_id` via `vector_map`
3. Implement visual search endpoint
4. Implement FTS5 query helpers
5. Implement text search endpoint
6. Add modality-specific search modes

## Done Criteria

1. Search visual hoạt động trên data-ready thật.
2. Search text hoạt động qua `text_documents`/FTS5 với caption, OCR, ASR, object, và metadata evidence.
3. Result resolve đúng về keyframe/video/frame.

## Validation

- deterministic sample queries
- result payload checks
- evidence checks

## Risks

- retrieval quality thấp do data, dễ bị nhầm là bug code;
- score semantics giữa modalities chưa normalize rõ.
