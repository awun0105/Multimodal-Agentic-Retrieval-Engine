# Phase 1 — System 1 Mini + Seed Dataset + Validation

## Status

Next implementation phase.

## Maps To

- `MVP-0.6`
- groundwork for `MVP-1`

## Goal

Implement một lát cắt nhỏ của System 1 để dùng **subset nhỏ từ data năm ngoái** tạo ra bộ app-ready artifacts đầu tiên.

Mục tiêu không phải ingest toàn bộ dataset ngay, mà là chứng minh:

- data contract có thể chạy thật;
- pipeline tối thiểu có thể tạo SQLite/media refs/report;
- app-ready artifacts đầu tiên đủ làm input thật cho System 2.

## Why This Phase Exists

Nếu nhảy thẳng sang System 2, team sẽ phải dùng mock hoặc giả định. Phase này tồn tại để chuyển dự án từ “docs đúng” sang “data thật đầu tiên đúng contract”.

## Scope

### A. Chọn subset data năm ngoái

- 1-2 video hoặc một phần dataset rất nhỏ
- vài keyframes tiêu biểu
- vài ví dụ caption/OCR/ASR/object/metadata nếu có

### B. Implement System 1 mini

Pipeline tối thiểu cần làm được:

- media discovery
- metadata normalization ở mức đủ dùng
- keyframe normalization
- thumbnail generation hoặc placeholder rõ ràng
- SQLite fixture/build output
- validation report

### C. Tạo app-ready outputs đầu tiên

Output mong muốn:

- processed media refs đúng contract
- `app.sqlite`
- FTS5 fixture tối thiểu hoặc seed text-search rows
- `vector_map` fixture tối thiểu
- validation report

## Suggested Issue Breakdown

1. Define last-year tiny subset scope
2. Create media discovery rules for subset
3. Normalize video/keyframe identity
4. Build minimal app-ready SQLite
5. Seed minimal evidence rows
6. Add validation checks
7. Emit validation report
8. Document how subset is built

## Done Criteria

1. Có subset nhỏ từ data năm ngoái được chọn rõ.
2. System 1 mini tạo được app-ready artifacts đầu tiên.
3. Validation report pass.
4. Team có input thật để thiết kế System 2, không còn chỉ dùng mock.

## Validation

- inspect generated artifact tree
- inspect `app.sqlite`
- verify logical refs
- verify `vector_map` resolution
- verify validator catches broken cases

## Risks

- chọn subset quá nhỏ, không đại diện;
- chọn subset quá to, làm chậm tiến độ;
- pipeline mini quá giả, không mở khóa phase sau.

## Dependencies For Next Phase

Phase 2 chỉ bắt đầu sau khi mini path chứng minh data contract chạy được trên subset thật.
