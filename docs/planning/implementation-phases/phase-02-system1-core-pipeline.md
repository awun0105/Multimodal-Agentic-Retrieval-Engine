# Phase 2 — System 1 Core Pipeline On Last-Year Data

## Maps To

- `SYS1-001`
- `SYS1-002`
- `SYS1-003`

## Goal

Mở rộng từ System 1 mini thành các pipeline lõi trên data năm ngoái:

- visual embeddings
- OCR + metadata normalization
- ASR transcription

## Main Question This Phase Answers

"Chúng ta có thể tạo được các modality outputs chính từ data năm ngoái theo dạng shard-safe, resumable, và có thể merge không?"

## Scope

### A. Vision embedding pipeline

- chọn model CLIP/OpenCLIP
- xử lý theo shard
- output embeddings/manifest trung gian

### B. OCR + metadata pipeline

- normalize organizer metadata
- import/generate OCR
- output shard-safe intermediate artifacts

### C. Audio transcription pipeline

- transcribe audio theo shard
- giữ `video_id`, `start_sec`, `end_sec`
- output ASR artifacts có thể merge

## Suggested Issue Breakdown

1. Implement visual embedding notebook/script
2. Implement OCR extraction flow
3. Implement metadata normalization flow
4. Implement ASR transcription flow
5. Add shard/resume strategy
6. Add output manifests for each modality

## Done Criteria

1. Có output trung gian cho visual pipeline.
2. Có output trung gian cho OCR/metadata pipeline.
3. Có output trung gian cho ASR pipeline.
4. Mỗi pipeline có rule naming, shard boundary, và resume logic tối thiểu.

## Validation

- sample shard runs
- output shape checks
- metadata/ID consistency checks
- ASR time-range sanity checks

## Risks

- data năm ngoái có format lệch giữa modalities;
- notebook/script khó reproduce;
- output trung gian không đủ ổn để merge.
