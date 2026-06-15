# Phase 3 — System 1 Aggregation And App-ready Artifact Builder

## Maps To

- `SYS1-004`
- remaining `MVP-1`

## Goal

Merge các output trung gian của System 1 thành bộ app-ready artifacts chính thức cho runtime:

- SQLite runtime DB
- FTS5 tables
- FAISS index
- `vector_map`
- `feature_availability`
- `release_capabilities`
- validation report

## Main Question This Phase Answers

"Từ các output rời rạc của pipeline, chúng ta đã build được bộ app-ready artifacts hoàn chỉnh cho System 2 chưa?"

## Scope

### A. Aggregation layer

- dùng DuckDB/staging nếu cần
- merge visual/OCR/ASR/metadata outputs
- build canonical IDs và joins

### B. Runtime artifact writing

- write `app.sqlite`
- write FTS5 tables
- write `embedding_indexes`
- write `vector_map`
- write `feature_availability`
- write `release_capabilities`
- write FAISS index + manifest

### C. Full validation

- no duplicate IDs
- no unresolved refs
- no broken vector mappings
- no absolute paths
- `video_ref`, `keyframe_ref`, and `thumbnail_ref` resolve through the media store
- `app.sqlite.vector_map` is the runtime source of truth; parquet mapping is debug/export mirror only
- evidence rows point đúng targets

## Suggested Issue Breakdown

1. Build DuckDB aggregation layer
2. Merge modality outputs into canonical tables
3. Write runtime SQLite artifacts
4. Build FTS5 tables
5. Build FAISS index and manifest
6. Write vector_map
7. Write feature availability and release capability tables
8. Emit full validation report

## Done Criteria

1. Có bộ app-ready artifacts hoàn chỉnh từ raw videos và metadata JSON đã pair/validate.
2. Validation report pass.
3. Team có thể trỏ System 2 vào artifact thật.
4. Không cần mock dataset để bắt đầu backend/UI nữa.

## Validation

- artifact directory inspection
- SQLite integrity checks
- `vector_map`/FAISS consistency checks
- feature availability and release capability checks
- FTS5 row checks
- report review

## Risks

- aggregation logic làm sai joins;
- FTS5/FAISS build outputs không đồng bộ;
- full dataset quá nặng, khó iterate nhanh.

## Dependencies For Next Phase

Phase 4 chỉ nên bắt đầu khi app-ready artifacts đã tồn tại thật và pass validation.
