# Phase 1 — System 1 Mini + Seed Dataset + Validation

## Status

Next implementation phase.

## Maps To

- `MVP-0.6`
- groundwork for `MVP-1`

## Goal

Implement một lát cắt nhỏ của System 1 để dùng **subset nhỏ gồm official videos
cùng metadata/support artifacts hữu ích khi có** tạo ra bộ app-ready artifacts
đầu tiên.

Mục tiêu không phải ingest toàn bộ dataset ngay, mà là chứng minh:

- data contract có thể chạy thật;
- video identity dùng filename stem làm `video_id` ổn định;
- metadata/support artifacts có thể được map vào video/frame khi có;
- pipeline tối thiểu có thể tạo SQLite/media refs/report;
- app-ready artifacts đầu tiên đủ làm input thật cho System 2.

## Why This Phase Exists

Nếu nhảy thẳng sang System 2, team sẽ phải dùng mock hoặc giả định. Phase này tồn tại để chuyển dự án từ “docs đúng” sang “data thật đầu tiên đúng contract”.

## Scope

### A. Chọn subset official videos và support artifacts

- 1-2 video hoặc một phần dataset rất nhỏ
- metadata JSON tương ứng cho từng video nếu có
- support artifacts của BTC nếu có và validate được mapping
- không assume keyframes/features/OCR/ASR/object từ ban tổ chức là đầy đủ hoặc đủ tốt

### B. Implement System 1 mini

Pipeline tối thiểu cần làm được:

- media discovery
- video identity theo filename stem
- optional metadata/support artifact mapping theo `video_id` / `frame_id`
- metadata normalization ở mức đủ dùng
- `video_ref` and logical media refs, without absolute paths in runtime DB
- frame probing with `fps_detected`, VFR flag/method metadata, and decoded-frame-count preference
- keyframe extraction từ raw video
- keyframe normalization
- thumbnail generation hoặc placeholder rõ ràng
- SQLite fixture/build output
- validation report

### C. Tạo app-ready outputs đầu tiên

Output mong muốn:

- processed media refs đúng contract
- `app.sqlite`
- normalized video registry với `video_id = source_video_stem`
- `video_ref`, `keyframe_ref`, and `thumbnail_ref` rows that resolve through the media store
- FTS5 fixture tối thiểu hoặc seed text-search rows
- `vector_map` fixture tối thiểu
- validation report

## Suggested Issue Breakdown

1. Define tiny official-source subset scope
2. Create video, metadata, and support artifact discovery rules
3. Validate stem-based `video_id` and support artifact mapping
4. Normalize video/keyframe identity
5. Extract minimal keyframes and thumbnails
6. Build minimal app-ready SQLite
7. Seed minimal evidence rows
8. Add validation checks
9. Emit validation report
10. Document how subset is built

## Done Criteria

1. Có subset nhỏ official videos và support artifacts được chọn rõ.
2. Identity validation pass: mỗi raw video có unique `video_id`; metadata/support artifacts present in the subset map cleanly or are excluded with warnings.
3. System 1 mini tạo được app-ready artifacts đầu tiên.
4. Validation report pass.
5. Team có input thật để thiết kế System 2, không còn chỉ dùng mock.

## Validation

- inspect generated artifact tree
- inspect `app.sqlite`
- verify video stem identity and optional metadata/support artifact mapping
- verify logical refs
- verify `video_ref` / derived logical refs resolve
- verify frame id/count method fields are present
- verify `vector_map` resolution
- verify validator catches broken cases

## Risks

- chọn subset quá nhỏ, không đại diện;
- chọn subset quá to, làm chậm tiến độ;
- pipeline mini quá giả, không mở khóa phase sau.

## Dependencies For Next Phase

Phase 2 chỉ bắt đầu sau khi mini path chứng minh data contract chạy được trên subset thật.
