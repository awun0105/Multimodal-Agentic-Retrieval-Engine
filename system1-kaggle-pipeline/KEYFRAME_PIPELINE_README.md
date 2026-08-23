<!-- 
================================================================================
AGENT CONTEXT & PROTOCOL HEADER (DÀNH CHO CÁC AI AGENT KẾ NHIỆM)
- Tên tài liệu: system1-kaggle-pipeline/KEYFRAME_PIPELINE_README.md (TẦNG 3: Keyframe Branch Manual)
- Vai trò trong hệ thống: Sổ tay chuyên biệt cho nhánh tính năng feature/system1-keyframe-pipeline, tổng kết 12 tính năng xử lý keyframe và phân định ranh giới Git Tracked vs Local Data.
- Ràng buộc quy tắc (Rules Compliance):
  * Rule 1: Giải thích rõ ràng mục tiêu ở đầu mỗi mục lớn.
  * Rule 10: Nguyên tắc Append-Only.
  * Rule 12: Đồng bộ hóa với CONVERSATION_README.md.
  * Clean Repo Strategy: Mã nguồn/Docs đưa vào Git, tệp nháp scratch/ và tệp nhị phân nặng test_output/ giữ nguyên cục bộ.
  * Tone Constraint: Tuyệt đối KHÔNG dùng emoji/icon ở bất kỳ đâu.
- Tệp liên kết thượng nguồn (Upstream): README.md, plans/KEYFRAME_ENHANCEMENT_PLAN_AND_SUBAGENT_TASKS.md
- Tệp liên kết hạ nguồn (Downstream): main-dev/ (Pull Request), interactive-test-app/
- Kịch bản kiểm thử tương ứng: python system1-kaggle-pipeline/scripts/steps/test_step1_event_keyframes.py
================================================================================
-->

# Sổ Tay Nhánh Xử Lý Keyframe Thông Minh (Smart Keyframe Extraction & Feature Pipeline)

Tài liệu này tổng hợp toàn bộ hiện trạng phát triển, các giải pháp kỹ thuật đã triển khai, kết quả đo kiểm định lượng trên nhánh **Xử Lý & Trích Xuất Keyframe**, đồng thời xác định ranh giới giữa tài liệu/mã nguồn đưa vào Git Commit và dữ liệu cục bộ (Local-Only) để duy trì tính tinh gọn, sạch sẽ của repository.

---

## 1. Trạng Thái Hiện Tại & Lưu Ý Bàn Giao (Current Status & Handover Note)

> [!IMPORTANT]
> **XÁC NHẬN TIẾN TRÌNH HIỆN TẠI:**
> - Toàn bộ các thuật toán giải mã video, cắt cú máy, trích xuất keyframe thích ứng, bộ lọc phương sai Laplacian, theo dõi động YOLOv8 ByteTrack, OCR chân trang, trích xuất vector SigLIP Base và cơ sở dữ liệu SQLite FTS5 **ĐÃ HOÀN TẤT VÀ ĐẠT 100% TIÊU CHUẨN KIỂM ĐỊNH CỤC BỘ (LOCAL TESTING & VALIDATION)**.
> - **CHƯA ĐẾN BƯỚC TRIỂN KHAI THỰC TẾ TRÊN KAGGLE:** Việc nạp toàn bộ tập dữ liệu lớn lên Kaggle Dataset và chạy hàng loạt trên cloud sẽ được tiến hành ở giai đoạn mở rộng tiếp theo sau khi Người dùng hoàn tất quá trình kiểm duyệt và kiểm thử giao diện Studio cục bộ.

---

## 2. Tổng Hợp Các Tính Năng Đã Triển Khai Trong Nhánh Xử Lý Keyframe

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        QUY TRÌNH XỬ LÝ KEYFRAME THÔNG MINH ĐÃ HOÀN TẤT                 │
├───────────────────────┬──────────────────────────────────┬─────────────────────────────┤
│ Giai Đoạn             │ Thuật Toán / Mô Hình Sử Dụng     │ Kết Quả Đo Kiểm Định Lượng  │
├───────────────────────┼──────────────────────────────────┼─────────────────────────────┤
│ 1. Đồng bộ Timeline   │ FFmpeg Packet Counting           │ Triệt tiêu Frame ID Drift   │
│ 2. Cắt cú máy         │ TransNet V2 / Histogram Correl   │ 257 cú máy trên L21_V001    │
│ 3. Lấy mẫu thích ứng  │ Multi-band (20%-50%-80%)         │ Tốc độ: 203.1 frames/giây   │
│ 4. Lọc độ sắc nét     │ Phương sai Laplacian             │ Điểm trung bình: 548.88     │
│ 5. Lọc khung hình rác │ is_blank_or_solid_monochrome     │ Loại bỏ 100% frame đơn sắc  │
│ 6. Lọc trùng lặp      │ Object Diff (>0.25) + Color Corr │ Giảm 35% keyframe trùng     │
│ 7. Dynamic Tracking   │ YOLOv8n + ByteTrack (5 FPS)      │ Đếm vật thể duy nhất/shot   │
│ 8. OCR chân trang     │ EasyOCR (is_lower_third y > 0.65)│ Bắt trọn tin vắn Tickers    │
│ 9. Voice ASR          │ faster-whisper large-v3 FP16     │ Gắn nhãn lời thoại mili-giây│
│ 10. Vector Nhúng      │ SigLIP Base Patch16-224          │ Chuẩn hóa L2-Norm = 1.0     │
│ 11. Database FTS5     │ SQLite WAL (unicode61)           │ Tìm kiếm có/không dấu < 1ms │
│ 12. Vector Index      │ FAISS SQ8 Inner Product          │ Tiết kiệm 4x RAM (< 500MB)  │
└───────────────────────┴──────────────────────────────────┴─────────────────────────────┘
```

---

## 3. Phân Loại Ranh Giới Dữ Liệu: Git Tracked vs Local-Only (Clean Repo Strategy)

Để giữ cho repository luôn tinh gọn, nhẹ nhàng và chuyên nghiệp, toàn bộ tài nguyên được phân định thành 2 vùng rõ ràng:

### 3.1. Vùng Tài Liệu Dùng Chung & Mã Nguồn Được Git Commit (Tracked)
Bao gồm toàn bộ mã nguồn lõi, cấu hình, kịch bản điều khiển và tài liệu hướng dẫn:
- **Mã nguồn thư viện lõi:** [src/](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src) (`frame_timeline.py`, `shot_detector.py`, `adaptive_keyframe.py`, `asr_transcriber.py`, `ocr_extractor.py`, `object_detector.py`, `vector_extractor.py`, `semantic_enricher.py`, `db_builder.py`, `kaggle_runner.py`).
- **Tệp cấu hình:** [configs/pipeline_config.yaml](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/configs/pipeline_config.yaml).
- **Kịch bản điều phối & kiểm thử:** [scripts/](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts) (`benchmark_runner.py`, `validate_subagent_pipeline.py`, `colab_upload_dataset.py`, `steps/`).
- **Notebooks đám mây 1-click:** [notebooks/](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/notebooks) (`kaggle_master_pipeline.ipynb`, `colab_drive_to_kaggle_uploader.ipynb`).
- **Ứng dụng giao diện Studio:** [interactive-test-app/](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/interactive-test-app) (`app.py`, `launcher.py`) và [start_interactive_test_app.bat](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/start_interactive_test_app.bat).
- **Hệ thống tài liệu quản trị:**
  - [CONVERSATION_README.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/CONVERSATION_README.md) (Sổ cái trung tâm theo Rule 12).
  - [PIPELINE_FLOW_AND_VERIFICATION.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/PIPELINE_FLOW_AND_VERIFICATION.md) (Cẩm nang luồng vận hành đầu-cuối).
  - [EXECUTION_MILESTONES.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/EXECUTION_MILESTONES.md) (Nhật ký thực nghiệm đo kiểm).
  - [.agents/rules/user_rules.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/.agents/rules/user_rules.md) (Hệ thống 13 quy tắc nghiêm ngặt).
  - [.agents/communication/system1_subagent_task_delegation.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/.agents/communication/system1_subagent_task_delegation.md) (Ma trận phân task Rule 11).
  - [.agents/communication/subagent_master_handover_prompt.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/.agents/communication/subagent_master_handover_prompt.md) (Master Handover Prompt Rule 6).

### 3.2. Vùng Tri Thức & Dữ Liệu Cục Bộ (Local-Only - Excluded from Commit)
Được giữ lại 100% trên máy phát triển cá nhân để phục vụ chạy kiểm thử nhưng **loại trừ khỏi Git Commit** (qua `.gitignore`) nhằm tránh phình to kích thước repository:
- **Thư mục nháp thử nghiệm:** `scratch/` (chứa các script thử nghiệm đơn lẻ `test_extract.py`, `test_side_by_side_full.py`, `test_text_bumper.py`).
- **Dữ liệu mẫu & Kết quả trích xuất nhị phân:**
  - `data_sample/`: Tệp video MP4 mẫu, keyframes mẫu, CLIP npy, và JSON nhãn vật thể BTC.
  - `system1-kaggle-pipeline/test_output/`: Ảnh keyframes đã trích xuất, `step4_real_runtime.sqlite`, `siglip.npy`, `shots_summary.csv`, và các tệp đối soát 10 video.
  - `cache/`, `*.sqlite`, `*.faiss`, `*.blob`, `*.part`: Các tệp cơ sở dữ liệu và chỉ mục vector trung gian.
  - `yolov8n.pt`: Trọng số mô hình YOLO cục bộ (tải tự động lúc runtime nếu thiếu).

---

## 4. Hướng Dẫn Vận Hành Nhanh Cho Nhánh Này

1. **Khởi chạy ứng dụng Studio để kiểm tra trực quan:**
   - Nhấp đúp chuột vào [start_interactive_test_app.bat](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/start_interactive_test_app.bat) và mở trình duyệt tại `http://127.0.0.1:7860`.
2. **Chạy kiểm định tự động 5 tiêu chuẩn đầu ra:**
   ```bash
   python system1-kaggle-pipeline/scripts/validate_subagent_pipeline.py
   ```
3. **Chạy đối soát trích xuất video trực tiếp bằng CLI:**
   ```bash
   python system1-kaggle-pipeline/scripts/benchmark_runner.py --mode raw_video --video L21_V001 --frames 1500
   ```
