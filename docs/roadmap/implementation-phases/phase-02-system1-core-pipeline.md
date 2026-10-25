# Phase 2 — System 1 Core Pipeline On Last-Year Data

## Maps To

- `SYS1-001`
- `SYS1-002`
- `SYS1-003`

## Goal

Mở rộng từ System 1 mini thành các pipeline lõi tự sinh trên official videos
cùng metadata khi có:

- separate SigLIP and BEiT3 embeddings
- TransNet V2 shot detection without silent production fallback
- frame timeline / timestamp-to-frame mapping for VFR safety
- Gemini OCR + metadata normalization
- faster-whisper large-v3 ASR transcription

## Main Question This Phase Answers

"Chúng ta có thể tạo được các modality outputs chính từ official videos theo
dạng shard-safe, resumable, và có thể merge
không?"

## Scope

### A. Vision embedding pipeline

- generate separate SigLIP and BEiT3 vectors
- xử lý theo shard
- output embeddings/manifest trung gian

### A2. Structure/timeline pipeline

- detect shots with TransNet V2; a successful no-cut result is one valid
  full-video shot, while production model/decode/inference failure fails the
  video after bounded retry
- build `frame_timeline` staging rows or equivalent mapping proof when accurate timestamp-to-frame mapping is needed
- extract distinct decoded frames near 20%/50%/80% of each shot and select the
  middle/early/late representative using versioned quality checks

### B. OCR + metadata pipeline

- normalize organizer metadata
- generate OCR with Gemini from System 1 keyframes
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
7. Add frame/timeline, no-cut, and production shot-failure validation

## Done Criteria

1. Có output trung gian cho visual pipeline.
2. Có output trung gian cho OCR/metadata pipeline.
3. Có output trung gian cho ASR pipeline.
4. Mỗi pipeline có rule naming, shard boundary, và resume logic tối thiểu.
5. Shot/timeline outputs preserve enough data to map time ranges to frame ids safely.

## Validation

- sample shard runs
- output shape checks
- metadata/ID consistency checks
- ASR time-range sanity checks
- timestamp-to-frame mapping checks using decoded frame ids when available

## Risks

- metadata/video pairing hoặc schema raw metadata có thể lệch giữa shards;
- notebook/script khó reproduce;
- output trung gian không đủ ổn để merge.
