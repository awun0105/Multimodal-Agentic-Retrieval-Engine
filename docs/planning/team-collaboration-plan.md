# Team Collaboration And Docs Validation Plan

## Mục tiêu

File này dùng để hướng dẫn teammate đọc hiểu repo và validate lại các docs quan trọng trước khi team tạo milestone/issue implementation.

Ý tưởng chính:

1. Tất cả teammate clone repo và làm việc từ branch `dev`.
2. Tất cả teammate đọc cùng một bộ docs source of truth dành cho human/team để hiểu toàn bộ dự án.
3. Sau đó team lead tạo các work package dưới dạng GitHub issue.
4. Mỗi teammate nhận một issue, validate một nhóm docs cụ thể, rồi gửi report.
5. Nếu cần chỉnh docs, teammate tạo branch mới từ `dev`, sửa docs, rồi mở pull request về `dev` kèm giải thích.
6. Team lead review report/PR và quyết định docs, milestone, issue tiếp theo.

Giai đoạn này **chưa ưu tiên code feature**. Mục tiêu là làm rõ hiểu biết chung và refine docs trước.

## Hướng triển khai hiện tại

Dự án đang đi theo hướng **System 1 trước System 2**:

```text
data contract
  -> System 1 mini trên subset official videos + support artifacts hữu ích khi có
  -> System 1 app-ready artifact builder
  -> System 2 runtime/API/UI/search
```

Lý do:

- System 2 chỉ có ý nghĩa khi đã có app-ready artifacts thật.
- Nếu làm backend/UI/search quá sớm, team sẽ build trên mock hoặc giả định.
- Data năm ngoái giúp validate contract, mapping, storage, và ingestion pipeline sớm.
- System 1 output sẽ là input thật cho System 2.

## Validate nghĩa là gì?

Validate docs nghĩa là kiểm tra:

1. Docs đã đủ chi tiết để teammate mới đọc hiểu chưa?
2. Có phần nào thiếu, sai, mâu thuẫn, hoặc khó hiểu không?
3. Lựa chọn hiện tại có hợp lý với bài toán và chương trình không?
4. Có đề xuất chỉnh docs, cách implement, chức năng, hoặc phase không?
5. Có issue nào nên tạo thêm không?

---

# Bước 1 — Setup cho tất cả teammate

Mỗi teammate làm:

```bash
git clone <repo-url>
cd Multimodal-Agentic-Retrieval-Engine
git checkout dev
git pull
```

Kiểm tra:

```bash
git status
```

Kỳ vọng:

```text
On branch dev
working tree clean
```

Nếu không ở branch `dev` hoặc working tree không clean, báo lại team lead trước khi làm tiếp.

---

# Bước 2 — Docs source of truth tất cả teammate phải đọc

Các file dưới đây là bộ docs tối thiểu để teammate hiểu toàn bộ dự án ở mức human/team. Không đưa các docs harness nội bộ, matrix, backlog, hoặc ADR chi tiết vào danh sách bắt buộc chung để tránh quá tải.

## 1. Tổng quan dự án

Đọc:

1. `README.md`
2. `docs/README.md`
3. `docs/architecture/overview.md`

Cần hiểu:

- project giải quyết bài toán gì;
- kiến trúc tổng quan gồm những phần nào;
- vì sao có System 1 và System 2.

## 2. Data contract và data model

Đọc:

1. `docs/onboarding/data-contract-explainer.md`
2. `docs/architecture/data-contracts.md`
3. `docs/architecture/storage-strategy.md`

Cần hiểu:

- app-ready data là gì;
- các loại data cần chuẩn bị;
- các bảng/quan hệ chính trong SQLite;
- embeddings, FAISS, FTS5, `vector_map` hoạt động thế nào;
- dữ liệu lưu ở đâu và vì sao dùng logical media refs.

## 3. System 1 và System 2

Đọc:

1. `docs/architecture/system1-ingestion.md`
2. `docs/architecture/system2-retrieval.md`

Cần hiểu:

- System 1 nhận raw data và tạo output gì;
- System 2 đọc input gì từ System 1;
- vì sao System 1 đi trước System 2.

## 4. Product/search/UI behavior

Đọc:

1. `docs/product/api-contracts.md`
2. `docs/product/query-workflows.md`
3. `docs/product/search-fusion.md`
4. `docs/product/ui-implementation.md`

Cần hiểu:

- API payload dự kiến;
- các query workflow chính;
- search visual/text/hybrid dự kiến;
- UI cần hỗ trợ inspect/save/export candidate như thế nào.

## 5. Phase plan dành cho team

Đọc:

1. `docs/planning/implementation-phases/README.md`
2. `docs/planning/implementation-phases/phase-01-system1-mini-seed-and-validation.md`
3. `docs/planning/implementation-phases/phase-02-system1-core-pipeline.md`
4. `docs/planning/implementation-phases/phase-03-system1-artifact-builder.md`
5. `docs/planning/implementation-phases/phase-04-system2-runtime-data-and-api.md`
6. `docs/planning/implementation-phases/phase-05-keyframe-first-ui.md`
7. `docs/planning/implementation-phases/phase-06-retrieval-foundations.md`

Cần hiểu:

- thứ tự làm việc hiện tại;
- phase nào là kế tiếp;
- phase nào phụ thuộc phase nào;
- vì sao chưa làm System 2 trước khi có app-ready artifacts.

---

# Bước 3 — General Understanding Report

Trước khi nhận work package, mỗi teammate gửi report ngắn cho team lead.

```text
# General Understanding Report

1. Project này đang giải quyết bài toán gì?
2. Theo bạn System 1 là gì?
3. Theo bạn System 2 là gì?
4. Vì sao System 1 nên đi trước System 2?
5. App-ready data là gì?
6. Các data chính cần chuẩn bị là gì?
7. `video_id`, `frame_id`, `keyframe_id`, `vector_id`, `media_ref` khác nhau thế nào?
8. SQLite, FTS5, FAISS, DuckDB, filesystem mỗi cái dùng để làm gì?
9. Search visual/text/hybrid khác nhau thế nào?
10. Phase tiếp theo của dự án nên là gì?
11. Phần nào bạn thấy khó hiểu nhất?
12. Bạn có đề xuất chỉnh docs, chức năng, hoặc thứ tự phase plan không, hoặc bất cứ đề xuất nào khác.
```

---

# Bước 4 — Work packages

Work package **không chia theo số lượng teammate**. Work package là một nhóm việc nhỏ để validate/refine docs.

Quy tắc:

1. Mỗi work package được tạo thành một GitHub issue riêng.
2. Mỗi work package chỉ chứa **tối đa 5 docs** để đọc sâu.
3. Một teammate chỉ nhận **một work package tại một thời điểm**.
4. Làm xong report hoặc PR cho work package hiện tại thì có thể nhận work package tiếp theo.
5. Work package nào có nhiều vấn đề thì tách thêm issue nhỏ hơn, không nhồi thêm docs vào cùng một issue.

Thứ tự ưu tiên đề xuất:

1. Nhóm data foundation: `WP-01` đến `WP-04`
2. Nhóm System 1: `WP-05` đến `WP-08`
3. Nhóm System 2/search/UI: `WP-09` đến `WP-13`
4. Nhóm phase/team workflow: `WP-14` đến `WP-16`

## Template chung cho mọi work package

Mỗi GitHub issue nên dùng cấu trúc này:

```text
# WP-XX — <Tên work package>

## Goal
Validate/refine nhóm docs này để kiểm tra nội dung đã rõ, đúng, đủ chi tiết và hợp lý chưa.

## Docs cần validate
- ...

## Checklist
- [ ] Đọc toàn bộ docs trong work package.
- [ ] Tóm tắt tôi hiểu gì từ docs.
- [ ] Ghi phần thiếu / sai / khó hiểu / mâu thuẫn.
- [ ] Ghi đề xuất chỉnh docs hoặc cách implement nếu có.
- [ ] Ghi candidate GitHub issues nếu có.
- [ ] Gửi report trong issue hoặc mở PR docs về `dev` nếu có chỉnh sửa.

## Report template
### Docs đã đọc
...

### Tôi hiểu gì
...

### Phần thiếu / sai / khó hiểu / mâu thuẫn
...

### Đề xuất chỉnh sửa
...

### Câu hỏi cho team lead
...

### Candidate issues
- Title:
  Reason:
  Expected output:
  Acceptance criteria:
```

---

## WP-01 — Project Overview And Human Reading Path

### Docs cần validate

- `README.md`
- `docs/README.md`
- `docs/architecture/overview.md`
- `docs/planning/implementation-phases/README.md`

### Trọng tâm validate

1. Người mới đọc có hiểu project làm gì không?
2. Reading path cho human/team đã rõ chưa?
3. System 1/System 2 được giải thích đủ dễ hiểu chưa?
4. Phase overview có khớp architecture overview không?
5. Có docs nào nên được link thêm/bớt trong overview không?

---

## WP-02 — App-ready Data Contract Core

### Docs cần validate

- `docs/onboarding/data-contract-explainer.md`
- `docs/architecture/data-contracts.md`
- `docs/architecture/storage-strategy.md`

### Trọng tâm validate

1. App-ready data là gì đã rõ chưa?
2. Các loại data cần chuẩn bị đã đủ chưa?
3. Storage roots và logical refs có dễ hiểu không?
4. SQLite/FTS5/FAISS/DuckDB/filesystem vai trò có rõ không?
5. Có phần nào quá dài, thiếu ví dụ, hoặc cần viết lại dễ hiểu hơn không?

---

## WP-03 — SQLite Relations And Data Mapping

### Docs cần validate

- `docs/onboarding/data-contract-explainer.md`
- `docs/architecture/data-contracts.md`
- `docs/product/api-contracts.md`

### Trọng tâm validate

1. Các bảng/quan hệ trong SQLite đã đủ rõ chưa?
2. Thuộc tính ví dụ cho từng quan hệ có hợp lý không?
3. Mapping `vector_id -> keyframe_id -> video_id/frame_id` có rõ không?
4. API payload có khớp data contract không?
5. Có thiếu field quan trọng nào cho System 2/UI không?

---

## WP-04 — Embeddings, Indexing, And Search Data Sources

### Docs cần validate

- `docs/onboarding/data-contract-explainer.md`
- `docs/architecture/data-contracts.md`
- `docs/product/search-fusion.md`
- `docs/architecture/system2-retrieval.md`

### Trọng tâm validate

1. CLIP/image embeddings lưu ở đâu đã rõ chưa?
2. Text embeddings hiện tại là future hay MVP requirement đã rõ chưa?
3. FAISS và FTS5 khác nhau thế nào đã rõ chưa?
4. Các data sources để search có đủ chưa?
5. Có đề xuất thêm/bỏ search source nào không?

---

## WP-05 — System 1 Mini Scope

### Docs cần validate

- `docs/architecture/system1-ingestion.md`
- `docs/planning/implementation-phases/phase-01-system1-mini-seed-and-validation.md`
- `docs/onboarding/data-contract-explainer.md`

### Trọng tâm validate

1. System 1 mini cần làm gì đã rõ chưa?
2. Dùng subset official videos + support artifacts hữu ích khi có có hợp lý không?
3. Output tối thiểu của mini path đã đủ chưa?
4. Có bước nào thiếu giữa raw data và app-ready artifacts không?
5. Work này có đủ nhỏ để tạo milestone/issue đầu tiên không?

---

## WP-06 — System 1 Core Pipeline

### Docs cần validate

- `docs/architecture/system1-ingestion.md`
- `docs/planning/implementation-phases/phase-02-system1-core-pipeline.md`
- `docs/architecture/ingestion.md`

### Trọng tâm validate

1. Media discovery, metadata normalization, OCR, ASR, embeddings có rõ không?
2. Shard/resume strategy có cần nói rõ hơn không?
3. Output trung gian của từng pipeline có rõ không?
4. Có pipeline nào nên tách issue riêng không?
5. Có rủi ro nào chưa được ghi?

---

## WP-07 — System 1 Artifact Builder And Validation

### Docs cần validate

- `docs/planning/implementation-phases/phase-03-system1-artifact-builder.md`
- `docs/architecture/data-contracts.md`
- `docs/architecture/system1-ingestion.md`

### Trọng tâm validate

1. Aggregation từ outputs trung gian sang app-ready artifacts đã rõ chưa?
2. SQLite/FTS5/FAISS/vector_map build flow có rõ không?
3. Validation report cần check gì đã đủ chưa?
4. Điều kiện mở khóa System 2 có rõ không?
5. Có edge case nào cần thêm?

---

## WP-08 — System 1 Risks And Operational Questions

### Docs cần validate

- `docs/architecture/technical-risks.md`
- `docs/architecture/system1-ingestion.md`
- `docs/planning/implementation-phases/phase-01-system1-mini-seed-and-validation.md`
- `docs/planning/implementation-phases/phase-02-system1-core-pipeline.md`

### Trọng tâm validate

1. Rủi ro ingest/index/cache/format drift đã đủ chưa?
2. Data năm ngoái có thể lệch data năm nay ở đâu?
3. Validation drift có cách kiểm soát chưa?
4. Có operational question nào cần team lead quyết định không?
5. Có candidate issue nào để giảm rủi ro không?

---

## WP-09 — System 2 Runtime API

### Docs cần validate

- `docs/architecture/system2-retrieval.md`
- `docs/product/api-contracts.md`
- `docs/planning/implementation-phases/phase-04-system2-runtime-data-and-api.md`

### Trọng tâm validate

1. System 2 input từ System 1 đã rõ chưa?
2. API payload có đủ cho UI/search không?
3. Endpoint dataset/keyframe/evidence/nearby đã đủ chưa?
4. Media URL/logical ref flow có rõ không?
5. Có API nào nên thêm/bỏ ở MVP không?

---

## WP-10 — Query Workflows

### Docs cần validate

- `docs/product/query-workflows.md`
- `docs/product/api-contracts.md`
- `docs/product/ui-implementation.md`

### Trọng tâm validate

1. TKIS/Q&A/TRAKE/VKIS có dễ hiểu không?
2. Current-only vs accumulated clues có rõ không?
3. Candidate save/export flow có hợp lý không?
4. TRAKE sequence và Q&A answer text có đủ rõ không?
5. Có workflow nào thiếu hoặc chưa hợp lý không?

---

## WP-11 — Search Fusion And Retrieval Strategy

### Docs cần validate

- `docs/product/search-fusion.md`
- `docs/architecture/system2-retrieval.md`
- `docs/planning/implementation-phases/phase-06-retrieval-foundations.md`

### Trọng tâm validate

1. Visual/text/hybrid search có rõ không?
2. Fusion weights có hợp lý cho MVP không?
3. Diversification/rerank top-K có cần đơn giản hóa không?
4. Evidence summary shape có đủ chưa?
5. Có search strategy nào nên research thêm không?

---

## WP-12 — UI Implementation And Candidate Workflow

### Docs cần validate

- `docs/product/ui-implementation.md`
- `docs/product/query-workflows.md`
- `docs/planning/implementation-phases/phase-05-keyframe-first-ui.md`
- `docs/planning/implementation-phases/phase-07-hybrid-workspace-output.md`

### Trọng tâm validate

1. UI layout có dễ hiểu không?
2. Candidate card/inspector/tray đã đủ field chưa?
3. Validation warnings có đủ chưa?
4. Output helper có rõ chưa?
5. Có UX nào nên thêm/bỏ ở MVP không?

---

## WP-13 — Agent Mode Scope

### Docs cần validate

- `docs/product/queries-and-agent.md`
- `docs/architecture/system2-retrieval.md`
- `docs/planning/implementation-phases/phase-08-agent-integration.md`

### Trọng tâm validate

1. Agent có đúng là layer trên cùng API/UI model không?
2. Tool calls và traceability có rõ không?
3. Human override có đủ rõ không?
4. Agent có nên để sau MVP retrieval không?
5. Có scope nào nên cắt bớt để tránh over-engineering không?

---

## WP-14 — Implementation Phase Plan

### Docs cần validate

- `docs/planning/implementation-phases/README.md`
- `docs/planning/implementation-phases/phase-01-system1-mini-seed-and-validation.md`
- `docs/planning/implementation-phases/phase-02-system1-core-pipeline.md`
- `docs/planning/implementation-phases/phase-03-system1-artifact-builder.md`
- `docs/planning/implementation-phases/phase-04-system2-runtime-data-and-api.md`

### Trọng tâm validate

1. Thứ tự phase có hợp lý không?
2. System 1 first rationale có rõ không?
3. Phase 1-4 có đủ goal/scope/done criteria không?
4. Có phase nào bị chồng chéo không?
5. Có milestone/issue nào nên tách nhỏ hơn không?

---

## WP-15 — Later Phase Plan And Scope Control

### Docs cần validate

- `docs/planning/implementation-phases/phase-05-keyframe-first-ui.md`
- `docs/planning/implementation-phases/phase-06-retrieval-foundations.md`
- `docs/planning/implementation-phases/phase-07-hybrid-workspace-output.md`
- `docs/planning/implementation-phases/phase-08-agent-integration.md`

### Trọng tâm validate

1. UI/retrieval/hybrid/agent phase order có hợp lý không?
2. Có phần nào nên defer khỏi MVP không?
3. Có phase nào thiếu done criteria không?
4. Có issue nào nên tạo để research trước không?
5. Có risk over-engineering không?

---

## WP-16 — Team Workflow And Issue Readiness

### Docs cần validate

- `docs/planning/team-collaboration-plan.md`
- `docs/planning/implementation-phases/README.md`
- `docs/README.md`

### Trọng tâm validate

1. Workflow clone -> read -> claim issue -> report -> PR có rõ không?
2. Work package có vừa sức một người không?
3. Report templates có dễ dùng không?
4. Có thiếu label/milestone/issue convention không?
5. File này có quá dài hoặc khó đọc không?

---

# Bước 5 — Quy trình nếu teammate muốn chỉnh docs

Nếu teammate chỉ validate và report, comment trực tiếp trong GitHub issue là đủ.

Nếu teammate muốn chỉnh docs, làm theo quy trình:

1. Cập nhật local `dev`:

```bash
git checkout dev
git pull
```

2. Tạo nhánh mới từ `dev`:

```bash
git checkout -b docs/<short-topic>
```

Ví dụ:

```bash
git checkout -b docs/clarify-system1-validation
```

3. Chỉ sửa đúng docs liên quan tới issue đang nhận.
4. Commit với message rõ ràng:

```bash
git add <files>
git commit -m "docs: clarify system1 validation plan"
```

5. Push branch và mở pull request về `dev`:

```bash
git push -u origin docs/<short-topic>
```

6. PR description cần có:

```text
## Vì sao sửa
...

## Đã sửa gì
...

## Docs liên quan
...

## Câu hỏi còn lại cho team lead
...
```

Team lead sẽ review trước khi merge.

---

# Bước 6 — Quy tắc làm việc

## Được làm

- Đọc docs nền tảng.
- Đọc sâu nhóm docs trong work package đã nhận.
- Comment nhận issue/work package.
- Ghi câu hỏi.
- Tạo report trong issue.
- Đề xuất chỉnh docs, phase, milestone, chức năng.
- Tạo branch docs và PR nếu team lead đồng ý hoặc issue yêu cầu.

## Không làm

- Không tự đổi schema/data contract nếu chưa được review.
- Không tự code feature trong vòng validate docs.
- Không sửa ngoài phạm vi issue đã nhận.
- Không merge trực tiếp vào `dev`.
- Không xóa/rename file nếu chưa hỏi team lead.

---

# Bước 7 — Quy trình rút gọn

1. Team lead gửi file này cho team.
2. Tất cả teammate clone repo và checkout `dev`.
3. Tất cả teammate đọc docs nền tảng.
4. Mỗi teammate gửi `General Understanding Report`.
5. Team lead tạo GitHub issues cho các work packages cần làm trước, bắt đầu từ `WP-01`.
6. Mỗi teammate nhận 1 work package.
7. Teammate gửi report trong issue.
8. Nếu cần chỉnh docs, teammate tạo branch từ `dev` và mở PR về `dev`.
9. Team lead tổng hợp report/PR và quyết định milestone/issue tiếp theo.
