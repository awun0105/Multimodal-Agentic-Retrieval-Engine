# Cấu trúc Dự án và Tiến độ: Multimodal Agentic Retrieval Engine

## 1. Tổng quan Kiến trúc (Architecture)
Dự án là một hệ thống truy xuất đa phương tiện (multimedia retrieval cockpit) trên nền web, phục vụ cho cuộc thi HCMC AI Challenge (AIC 2026). Kiến trúc tổng thể bao gồm các công nghệ:

*   **Frontend**: React + TypeScript + Vite.
*   **Backend**: Python + FastAPI.
*   **Cơ sở dữ liệu (DB)**: 
    *   Metadata và text search (tìm kiếm theo từ khóa/object): Sử dụng **SQLite (FTS5)**.
    *   Vector search: Sử dụng **FAISS** để tối ưu tìm kiếm trên CPU.
*   **Xử lý Media**: Quản lý file trên hệ thống (File system) kết hợp với **FFmpeg**.
*   **Môi trường chạy**: Docker Compose, hỗ trợ chạy Local (trên 1 máy) hoặc LAN (chia sẻ chung một UI qua mạng nội bộ cho cả đội).

Về mặt giải pháp cho cuộc thi, hệ thống được thiết kế theo 3 tầng (theo tài liệu `aic_2026_problem_and_tech_requirements.md`):
1.  **Tầng 1 (Nền móng - Base Pipeline)**: Ingest Data (Keyframes, CLIP features có sẵn từ BTC), Indexing bằng FAISS, Search cơ bản và UI hiển thị.
2.  **Tầng 2 (Nâng cấp - Advanced Filtering)**: Kết hợp lọc bằng Metadata, bổ sung OCR & Object Detection lên Keyframes và xử lý mượt mà tác vụ TRAKE.
3.  **Tầng 3 (AI Agent & RAG - Nâng cao)**: Đưa LLM vào làm Agent điều phối và hệ thống tương tác Chat để trả lời Q&A.

## 2. Ý nghĩa và Mục tiêu của các thư mục/file chính

*   **`README.md` (Gốc)**: Giới thiệu ngắn gọn tổng quan về dự án, công nghệ và các chế độ chạy.
*   **`docs/`**: Đây là bộ não tài liệu của dự án. Theo chuẩn *Project Harness*, thư mục này là nguồn sự thật (source of truth) dùng chung cho cả con người và AI Agent.
    *   `docs/product/`, `docs/requirements/`, `docs/architecture/`: Mô tả hành vi sản phẩm, yêu cầu kỹ thuật và kiến trúc.
    *   `docs/planning/`, `docs/stories/`, `docs/decisions/`: Theo dõi kế hoạch, các task (stories) và ghi nhận những quyết định kỹ thuật lớn.
    *   `docs/validation/`: Chứa ma trận kiểm thử (test matrix), đảm bảo tính đúng đắn khi thay đổi code.
    *   `docs/harness/`: Quy định cách AI Agent hoạt động (Agent operating rules), các template tài liệu chuẩn để thống nhất cách làm việc.
*   **`scripts/`**: Chứa các đoạn script tiện ích, công cụ dòng lệnh (`bin/harness-cli`) và thư mục `scripts/legacy_2025/` lưu trữ các mã nguồn tái sử dụng từ dự án AIC 2025 (Query Rewriter, TRAKE DP Solver, BEiT-3 wrapper, Data Migration scripts).
*   **`ui-ideas/`**: Chứa các file ảnh (mockup) mô phỏng ý tưởng giao diện (ví dụ: `automatic.png`, `interactive.png`).
*   **`.agent/`**: Nơi lưu trữ tài liệu phân tích, ghi chú phục vụ nội bộ cho Agent và các tác vụ cụ thể:
    *   `aic_2026_problem_and_tech_requirements.md`: Đã phân tích cụ thể đề thi AIC 2026 (3 dạng toán: KIS, Q&A, TRAKE), đưa ra chiến thuật ưu tiên CPU-only, chạy offline (Local-first).
    *   `Ban_chia_viec_nghien_cuu_multimodal.md`: Kế hoạch và phân công nghiên cứu các mô hình AI (R&D).
    *   `previous_year_learnings.md`: Tổng hợp bài học kinh nghiệm và hướng dẫn tái sử dụng mã nguồn AIC 2025 cho chủ đề Thể thao (Sports) năm 2026.
    *   `project_structure_and_progress.md`: (File này) Tổng hợp kiến trúc, mục tiêu các file và tiến độ dự án.

## 3. Các Nhánh (Branches) & Tiến độ Cập nhật Mới Nhất trên GitHub

Repository [awun0105/Multimodal-Agentic-Retrieval-Engine](https://github.com/awun0105/Multimodal-Agentic-Retrieval-Engine) hiện có các nhánh phát triển chính:
*   **`master` (Branch chính mặc định)**: Chứa bộ khung hệ thống, ma trận kiểm thử (Project Harness), System 1 Spec và tài liệu thiết kế tổng thể.
*   **`dev` (Branch phát triển active - Đi trước `master` 90+ commits)**: Chứa toàn bộ các cập nhật tính năng mới nhất về Data Ingestion Pipeline, OCR/ASR Research, và các mô hình VLM mới.
*   **`system1` & `system1-notebook01`**: Nhánh chuyên sâu xây dựng Pipeline tiền xử lý dữ liệu thô (Phase 00 & Phase 01).
*   **`implementation/web-retrieval-system`**: Nhánh phát triển giao diện Web UI (React/Vite) + Backend API (FastAPI) + FAISS Search.

### Các Tính Năng & Nghiên Cứu Mới Đã Thêm (Trích xuất từ `dev` branch):
1.  **Mở rộng Thử nghiệm VLM & OCR thế hệ mới**: Đã tích hợp các benchmark cho mô hình **Vintern-1B** (VLM tiếng Việt tối ưu) và **Qwen2-VL** vào tập nghiên cứu OCR/Captioning.
2.  **Hệ thống System 1 Pipeline (Phase 00 & Phase 01)**:
    *   Tự động hóa đồng bộ dữ liệu thô qua **Hugging Face Hub** & **Google DriveFS**.
    *   Tích hợp kĩ thuật **Packet Counting** khi decode video bằng FFmpeg để triệt tiêu hoàn toàn hiện tượng lệch khung hình (**Frame ID Drift**).
    *   Xây dựng hệ thống **Checkpoint & Restore CLI** giúp lưu tiến trình và khôi phục dễ dàng khi xử lý tập dữ liệu video khổng lồ.
3.  **Chuẩn hóa Shot Caption & Ranh giới Tìm kiếm Thời gian (Temporal Search Boundary)**: Cung cấp API contract rõ ràng cho System 2 (Retrieval Engine) truy vấn theo mốc thời gian.

## 4. Tóm Tắt Trạng Thái Hiện Tại (Current Status)

- **Bộ khung & Luật chơi (Docs / Harness / Architecture):** Đã hoàn chỉnh trên nhánh `master`.
- **Hệ thống nạp & Tiền xử lý dữ liệu (System 1 Ingestion Pipeline):** Đã hoàn thiện luồng xử lý trên nhánh `dev` & `system1`.
- **Thử nghiệm AI Models (Embedding, OCR/ASR, VLM):** Đã mở rộng thêm các mô hình hàng đầu (Vintern-1B, Qwen2-VL, Whisper, Florence-2).
- **Hệ thống Web UI & Backend (System 2 Retrieval Engine):** Đã có bản dựng giao diện tìm kiếm trên nhánh `implementation/web-retrieval-system`.
