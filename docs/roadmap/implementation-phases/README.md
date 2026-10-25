# Implementation Phases Plan

## Mục đích

Bộ tài liệu này là kế hoạch triển khai theo phase của dự án, viết để làm nguồn tạo:

- GitHub milestones
- GitHub issues theo phase
- checklist giao việc
- thứ tự implement và validate

Các phase ở đây bám theo canonical backlog, nhưng được **tổ chức lại theo hướng System 1 trước, System 2 sau**.

## Vì sao chọn hướng System 1 trước

Sau khi chốt `MVP-0.5 App-ready Data Contract`, bước hợp logic tiếp theo không phải là dựng backend/UI ngay, mà là:

1. implement System 1 ở mức nhỏ trước;
2. dùng subset official videos cùng metadata khi có để tạo app-ready artifacts;
3. validate các artifacts đó;
4. rồi mới dựng System 2 trên dữ liệu đã có thật.

Lý do:

- System 2 chỉ có ý nghĩa khi đã có SQLite/FTS5/FAISS/media refs đúng contract.
- Nếu làm System 2 quá sớm, team sẽ build trên mock hoặc giả định.
- Data năm ngoái là nguồn rất tốt để test contract, mapping, và validation.
- Cách này giúp phát hiện sớm chỗ khó của pipeline ingest thay vì phát hiện muộn ở UI/API.

## Nguyên tắc chia phase

1. Đi từ **data contract -> System 1 -> app-ready artifacts -> System 2**.
2. Đi từ **subset nhỏ có thể kiểm chứng** trước, rồi mới mở rộng pipeline đầy đủ.
3. Chỉ mở phase sau khi phase trước đã đủ output để phase sau không build trên giả định mơ hồ.
4. Mỗi phase phải trả lời rõ:
   - làm gì;
   - xong thì được gì;
   - phụ thuộc gì;
   - rủi ro gì;
   - cần evidence gì.

## Bản đồ phase

| Phase | Tên | Gắn với backlog |
| --- | --- | --- |
| Phase 0 | Canonical Foundation | `MVP-0`, `MVP-0.5` |
| Phase 1 | System 1 Mini + Seed Dataset + Validation | `MVP-0.6`, groundwork `MVP-1` |
| Phase 2 | System 1 Core Pipeline On Last-Year Data | `SYS1-001`, `SYS1-002`, `SYS1-003` |
| Phase 3 | System 1 Aggregation And App-ready Artifact Builder | `SYS1-004`, phần còn lại `MVP-1` |
| Phase 4 | System 2 Runtime Data And API Backbone | `MVP-2`, `SYS2-001` |
| Phase 5 | Keyframe-first UI Vertical Slice | `MVP-3`, `SYS2-002` |
| Phase 6 | Retrieval Foundations | `MVP-4`, `MVP-5`, `SYS2-003`, `SYS2-004` |
| Phase 7 | Hybrid Search, Workspace, And Output | `MVP-6`, `MVP-7`, `MVP-8` |
| Phase 8 | Agent Integration | `MVP-9`, `SYS2-005` |

## Cách dùng bộ plan này

1. Đọc `phase-01-system1-mini-seed-and-validation.md` trước khi bắt đầu code.
2. Mỗi phase có thể tách thành 3-10 GitHub issues nhỏ hơn.
3. Khi mở issue, giữ nguyên:
   - objective
   - scope
   - dependencies
   - done criteria
   - validation
4. Không mở issue implementation cho System 2 nếu chưa có app-ready artifacts đủ dùng từ System 1.

## Current State

Hiện tại dự án đã hoàn thành ở mức docs:

- `MVP-0` implemented
- `MVP-0.5` implemented

Phase tiếp theo nên làm là:

- **Phase 1 — System 1 Mini + Seed Dataset + Validation**

## File trong thư mục này

- `phase-00-canonical-foundation.md`
- `phase-01-system1-mini-seed-and-validation.md`
- `phase-02-system1-core-pipeline.md`
- `phase-03-system1-artifact-builder.md`
- `phase-04-system2-runtime-data-and-api.md`
- `phase-05-keyframe-first-ui.md`
- `phase-06-retrieval-foundations.md`
- `phase-07-hybrid-workspace-output.md`
- `phase-08-agent-integration.md`
