# SESSION HANDOVER & COMMUNICATION LOG (CHUYỂN NHƯỢNG BỐI CẢNH DỰ ÁN)

**Ngày khởi tạo:** 06/08/2026  
**Dự án:** Multimodal Agentic Retrieval Engine (AIC 2026 - Chủ đề Thể thao / Sports)  
**Nhánh Git hiện tại:** `dev`  
**Mục đích:** Lưu lại toàn bộ bối cảnh, các mốc giao tiếp giữa User và AI Agent, danh sách công việc đã làm để có thể dễ dàng Copy-Paste sang các LLM/Agent khác (Gemini, ChatGPT, Claude) để làm việc tiếp hoặc thực hiện Cross-Validation.

---

## 🤖 PROMPT CHUYỂN NHƯỢNG CHO MODEL MỚI (COPY-PASTE READY)

> *Hãy copy đoạn text trong khung này và dán vào ChatGPT / Claude / Gemini khi mở phiên chat mới:*
>
> ```text
> Bạn là AI Assistant đang pair programming hỗ trợ tôi trong dự án "Multimodal Agentic Retrieval Engine" cho cuộc thi HCMC AI Challenge (AIC 2026 - Chủ đề Thể thao).
> Tôi đã thiết lập file quy tắc làm việc tại `.agent/user_rules.md` và `AGENTS.md`. Hãy đọc file `.agent/communication/session_handover_20260806.md` để nắm toàn bộ bối cảnh dự án, các quyết định kiến trúc Dual-Stream (Local SigLIP + Cloud API), mã nguồn mảng Embedding đã viết trong `system1/research/embedding/` và tiếp tục hỗ trợ tôi theo đúng các quy tắc cá nhân đã đề ra!
> ```

---

## I. Tóm Tắt Yêu Cầu Của User & Các Mốc Quan Trọng (Milestones)

1. **Mốc 1 - Đọc hiểu & Tổng hợp Kiến trúc Dự án:**
   - Đã tạo file [.agent/project_structure_and_progress.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine-master/Multimodal-Agentic-Retrieval-Engine-master/.agent/project_structure_and_progress.md) tổng hợp kiến trúc hệ thống (React/Vite + FastAPI + SQLite FTS5 + FAISS Vector Search + Docker).
2. **Mốc 2 - Trích xuất Dữ liệu & Code Bài Làm Năm Ngoái (AIC 2025):**
   - Đã lưu trữ mã nguồn 2025 vào [scripts/legacy_2025/](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine-master/Multimodal-Agentic-Retrieval-Engine-master/scripts/legacy_2025/) bao gồm `query_rewrite_service.py`, `video_ranking_service.py` (DANTE DP solver), `model_service.py` (L2 norm) và `keyframe_migration.py`.
   - Đã tổng hợp bài học tại [.agent/previous_year_learnings.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine-master/Multimodal-Agentic-Retrieval-Engine-master/.agent/previous_year_learnings.md).
3. **Mốc 3 - Đồng bộ Branch Git trên GitHub:**
   - Đã `git fetch` và chuyển làm việc trực tiếp trên nhánh active **`dev`** ([awun0105/Multimodal-Agentic-Retrieval-Engine](https://github.com/awun0105/Multimodal-Agentic-Retrieval-Engine)).
4. **Mốc 4 - Thiết lập File Quy tắc Cá nhân (`.agent/user_rules.md` & `AGENTS.md`):**
   - Đã định nghĩa quy tắc trình bày: Giải thích bước ở đầu mục lớn, phân tích và lên kế hoạch trước khi code, chủ động đặt câu hỏi khi cần cập nhật thông tin (đến 07/2026).
   - Đã bổ sung các quy tắc chiến lược: Model Escalation (Gemini Pro/Claude/GPT-4o), Cross-Validation, Translation API, Prompt Optimizer Sub-Agent và Dual-Stream Hybrid Architecture.
5. **Mốc 5 - Triển khai Mảng Embedding & Prompt Optimizer Sub-Agent:**
   - Đã tạo thư mục và viết thành công 5 file mã nguồn tại `system1/research/embedding/`.
   - Đã chạy thử nghiệm `benchmark.py` qua `uv` đạt kết quả thành công 100%.
6. **Mốc 6 - Trích Xuất Mở Rộng 1,896 Keyframes Đầy Đủ Metadata Truy Ngược (Video ID & Frame ID):**
   - Đã nâng cấp `scripts/inspect_data.py` trích xuất 1,896 ảnh keyframes thuộc 10 thư mục video (`L26_V200` đến `L26_V209`).
   - Đã khởi tạo file ánh xạ metadata [`data/benchmark_samples/metadata_map.json`](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine-master/Multimodal-Agentic-Retrieval-Engine-master/data/benchmark_samples/metadata_map.json).
   - Đã cập nhật `test_real_retrieval.py` cho kết quả tìm kiếm chuẩn định dạng nộp bài (Video ID, Frame ID, Keyframe ID, Image Path) chỉ trong 121 ms!
7. **Mốc 7 - Xác Nhận Hợp Lệ & Tối Ưu Chiến Lược Human-in-the-Loop (Interactive Cockpit):**
   - Đã xác nhận thể lệ AIC **HOÀN TOÀN CHO PHÉP** con người tương tác duyệt và lọc kết quả.
   - Đã đưa quy tắc thiết kế giao diện Interactive Cockpit (Hover preview, Timeline slider, Negative relevance feedback) vào `.agent/user_rules.md` và `AGENTS.md`.
8. **Mốc 8 - Giải Mã 8 File ZIP, Trích Xuất 5 File Mẫu Kiểm Thử & Tạo Master Prompt Mới:**
   - Đã tạo tài liệu README & Connection Map giải thích 8 file ZIP tại [`data/AIC_2025_some_zip/README_ZIP_DATASET.md`](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine-master/Multimodal-Agentic-Retrieval-Engine-master/data/AIC_2025_some_zip/README_ZIP_DATASET.md).
   - Đã trích xuất 3 file cố định + 2 file ngẫu nhiên vào thư mục [`data/verification_samples/`](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine-master/Multimodal-Agentic-Retrieval-Engine-master/data/verification_samples/) để User mở ra xem duyệt trực tiếp.
   - Đã khởi tạo Master Prompt sẵn sàng Copy-Paste tại [`.agent/communication/new_chat_master_prompt.md`](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine-master/Multimodal-Agentic-Retrieval-Engine-master/.agent/communication/new_chat_master_prompt.md).

---

## II. Danh Mục Mã Nguồn Đã Thực Hiện (Code Artifacts)

### 1. File Quy tắc & Giao tiếp:
- [.agent/user_rules.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine-master/Multimodal-Agentic-Retrieval-Engine-master/.agent/user_rules.md): File quy tắc cá nhân đầy đủ 6 mục.
- [AGENTS.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine-master/Multimodal-Agentic-Retrieval-Engine-master/AGENTS.md): Đã cập nhật User Personal Rules.
- [.agent/how_it_works_and_execution_guide.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine-master/Multimodal-Agentic-Retrieval-Engine-master/.agent/how_it_works_and_execution_guide.md): Tài liệu hướng dẫn đọc hiểu sản phẩm và luồng code chạy.
- [.agent/communication/session_handover_20260806.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine-master/Multimodal-Agentic-Retrieval-Engine-master/.agent/communication/session_handover_20260806.md): (File này) Nhật ký chuyển nhượng bối cảnh.

### 2. File Module Nghiên cứu Embedding (`system1/research/embedding/`):
- `translator.py`: Query Translation API (Vietnamese -> English).
- `prompt_optimizer.py`: Sub-Agent làm giàu Prompt Thể thao + bước xác nhận với User.
- `extractor.py`: SigLIP/CLIP Embedding Extractor với **L2 Normalization** chuẩn.
- `benchmark.py`: Script kiểm thử tự động toàn bộ luồng.
- `report.md`: Báo cáo nghiên cứu mảng Embedding.

---

## III. Các Thống Nhất Về Kiến Trúc Đang Áp Dụng

1. **Chiến lược Dual-Stream Hybrid (Tốc độ + Độ chính xác):**
   - **Stream A (Local):** SigLIP Base / FAISS tại Local -> Trả về kết quả xem trước trên UI ngay tức thì (< 100ms).
   - **Stream B (Cloud API):** Gemini 3.1 Pro / GPT-4o / Claude API -> Làm giàu Prompt sâu và re-rank lại Top K (< 1-2s).
   - **Fallback:** Tự động rơi về Stream A nếu mạng gián đoạn.
2. **Chiến lược Data Processing:**
   - **Pre-compute Heavy:** Offline VLM Captioning (Vintern-1B, Qwen2-VL), OCR (Florence-2), ASR (Whisper) thực hiện trước cuộc thi.
   - **Live Query Light:** Mô hình tìm kiếm trực tiếp siêu nhẹ để tiết kiệm thời gian phản hồi.
