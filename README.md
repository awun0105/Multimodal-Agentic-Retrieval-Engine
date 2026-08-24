# MULTIMODAL AGENTIC RETRIEVAL ENGINE & INGESTION PIPELINE (AIC 2026)

Hệ thống Tìm kiếm Truy xuất Video Đa Phương Thức Thông Minh (Multimodal Agentic Retrieval Engine) và Phân Hệ Tiền Xử Lý / Trích Xuất Keyframe Video (Video Ingestion Pipeline) được thiết kế chuyên biệt phục vụ cuộc thi **AI Challenge (AIC) 2026**.

**GitHub Repository:** [awun0105/Multimodal-Agentic-Retrieval-Engine](https://github.com/awun0105/Multimodal-Agentic-Retrieval-Engine)  
**Nhánh Triển Khai Chính:** `feature/system1-keyframe-pipeline`  
**Đường Dẫn Tạo Pull Request:** [Tạo Pull Request trên GitHub](https://github.com/awun0105/Multimodal-Agentic-Retrieval-Engine/pull/new/feature/system1-keyframe-pipeline)  
**Báo Cáo Kỹ Thuật Đầy Đủ:** [KEYFRAME_EXTRACTION_AND_PROCESSING_REPORT.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/KEYFRAME_EXTRACTION_AND_PROCESSING_REPORT.md)  
**Trạng Thái Kiểm Định Thực Nghiệm:** **100% ALL PASS (7/7 Step Suites, 51/51 Test Cases)**

---

## 1. Phân Định Ranh Giới Nhiệm Vụ (Scope Boundary)

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│               PHẦN 1: TRỌNG TÂM CỐT LÕI - TÁCH & XỬ LÝ KEYFRAME (PRIMARY SCOPE)         │
│                         (ĐÃ HOÀN THÀNH 100% CHUẨN XÁC VÀ ĐÓNG GÓI)                     │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 1. Trích xuất cú máy thích ứng (HSV Color Histogram 32x32, Chi-Square, min_shot=0.6s)   │
│ 2. Khống chế trần lấy mẫu tối đa (Max Sampling Gap <= 2.5s, xóa bỏ hiện tượng thiếu ảnh)│
│ 3. Chọn frame nét nhất (Max Laplacian Variance > 30.0) & Cứu ảnh mờ (Unsharp Mask)     │
│ 4. Kích hoạt biến động ngữ nghĩa (YOLO In/Out Trigger, HSV Appearance, OCR Text Change)│
│ 5. Hợp nhất dòng thời gian đa tầng với BTC (Anchor, Frame Cắt Nghĩa, Đề Xuất Lọc Bỏ)   │
│ 6. Nén lưu trữ WebP 85% (Tiết kiệm 80% dung lượng) & In-Memory Zip Caching RAM O(1)    │
│ 7. Triệt tiêu sạch cảnh báo C-level FFmpeg (silence_stderr & LOG_LEVEL_SILENT)          │
└──────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │ (Đầu ra: Bộ ảnh WebP & Timeline Parquet/SQLite)
┌──────────────────────────────────────────▼─────────────────────────────────────────────┐
│          PHẦN 2: CÁC Ý TƯỞNG & TÍNH NĂNG MỞ RỘNG (DOWNSTREAM RETRIEVAL EXTENSIONS)     │
│                         (ĐÃ TRIỂN KHAI GIỮA CHỪNG - DÀNH CHO ROADMAP SAU)              │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ - Trích xuất vector nhúng SigLIP SO400M (1152d) / ViSigLIP (768d) & Đánh FAISS Index   │
│ - Bóc tách âm thanh tiếng Việt bằng Whisper Large-v3 Turbo kèm Word Timestamps        │
│ - Nhận diện chữ sâu bằng VLM (Vintern-1B, Qwen2-VL-2B) cho bảng biểu và đồ họa phức tạp│
│ - Bộ từ điển văn hóa bản địa (Vietnamese Cultural Lexicon & Faithful Query Enricher)   │
│ - Công cụ tìm kiếm KIS Sub-200ms kết hợp SigLIP + SQLite FTS5 BM25                    │
│ - Cơ chế Dual-Stream Re-ranking gọi Cloud API (Gemini / Claude) khi có Internet        │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Các Tập Lệnh Vận Hành 1-Click Cốt Lõi (`.bat` Files)

Để giữ cho thư mục gốc gọn gàng và dễ sử dụng, hệ thống đã tinh gọn và chỉ lưu giữ **2 tập lệnh `.bat` quan trọng nhất**:

| Tập Lệnh `.bat` | Chức Năng Vận Hành | Hướng Dẫn Sử Dụng |
| :--- | :--- | :--- |
| [start_interactive_test_app.bat](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/start_interactive_test_app.bat) | **Khởi chạy Giao diện Interactive Cockpit Studio (Port 7860)**<br>- Tự động kiểm tra và dọn dẹp port 7860 nếu bị chiếm dụng.<br>- Khởi động web server Gradio Blocks trên `http://127.0.0.1:7860`.<br>- Tự động mở trình duyệt sau 1.2s với console 100% sạch bóng cảnh báo C-level. | Nhấp đúp trực tiếp vào tệp hoặc chạy từ terminal:<br>`.\start_interactive_test_app.bat` |
| [run_all_system1_step_tests.bat](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/run_all_system1_step_tests.bat) | **Kiểm định thực nghiệm toàn diện 1-Click (100% ALL PASS)**<br>- Tự động chạy tuần tự toàn bộ 7 Step Test Suites (51 test cases) với dữ liệu thật.<br>- Kiểm tra Video Ingestion, Adaptive Keyframe, OCR, Whisper, Timeline Merge/Dedup, Lexicon, và E2E Studio Runtime. | Nhấp đúp trực tiếp vào tệp hoặc chạy từ terminal:<br>`.\run_all_system1_step_tests.bat` |

---

## 3. Bản Đồ Cấu Trúc Thư Mục & Phân Hệ

```text
Multimodal-Agentic-Retrieval-Engine/
│
├── start_interactive_test_app.bat                      # [BAT 1] Chạy Web Cockpit Studio trên localhost
├── run_all_system1_step_tests.bat                      # [BAT 2] Chạy bộ test 7/7 Step Suites 100% ALL PASS
├── KEYFRAME_EXTRACTION_AND_PROCESSING_REPORT.md        # Báo cáo kỹ thuật tổng kết và tài liệu Pull Request
├── CONVERSATION_README.md                              # Sổ cái trung tâm ghi nhận lịch sử 44+ tính năng
├── README.md                                           # Cẩm nang tổng quan hệ thống
│
├── interactive-test-app/                               # PHÂN HỆ GIAO DIỆN COCKPIT STUDIO
│   ├── app.py                                          # Entrypoint lắp ráp Gradio Blocks & Port Manager
│   ├── services/                                       # Tầng 2: Nghiệp vụ dữ liệu & Thuật toán
│   │   ├── config.py                                   # Hằng số và đường dẫn tệp zip/output
│   │   ├── model_service.py                            # Nạp YOLO, Zip Cache RAM O(1), Silence Stderr
│   │   ├── timeline_service.py                         # Cắt cú máy video thô, Render Side-by-Side
│   │   ├── appearance_service.py                       # Phân tích dải màu HSV & Bắt biến động vật thể
│   │   ├── caption_service.py                          # Caption Decoupled Dual-Channel khách quan
│   │   └── persistence_service.py                      # Thống kê dung lượng WebP & Xuất CSV
│   ├── components/                                     # Tầng 1: Giao diện 5 Tabs độc lập
│   │   ├── tab1_side_by_side.py                        # Tab 1: So sánh Timeline Side-by-Side với BTC
│   │   ├── tab2_storage_hub.py                         # Tab 2: Quản lý bộ nhớ WebP
│   │   ├── tab3_multimodal_matrix.py                   # Tab 3: Ma trận soi Steps 1-6
│   │   ├── tab4_hybrid_search.py                       # Tab 4: Giao diện tìm kiếm (Phần mở rộng)
│   │   └── tab5_parameter_tuning.py                    # Tab 5: Tùy chỉnh tham số cắt cảnh
│   └── templates/                                      # Tầng 3: Giao diện Dracula/Nord Dark Theme
│
├── system1-kaggle-pipeline/                            # PHÂN HỆ TIỀN XỬ LÝ DỮ LIỆU & KEYFRAME PIPELINE
│   ├── README.md                                       # Cẩm nang kỹ thuật chi tiết của System 1
│   ├── src/                                            # Mã nguồn thuật toán lõi
│   │   ├── shot_detector.py                            # Cắt cú máy HSV Color Histogram 32x32 bins
│   │   ├── adaptive_keyframe.py                        # Trần lấy mẫu 2.5s, Laplacian Sharpness & Unsharp Mask
│   │   ├── timeline_synchronizer.py                    # Hợp nhất Timeline với BTC & Phân cấp 4 vai trò
│   │   ├── object_detector.py                          # YOLOv8 + Bóc tách dải màu HSV (áo/xe)
│   │   ├── ocr_extractor.py                            # PaddleOCR v4 phát hiện trùng hình khác chữ
│   │   ├── frame_timeline.py                           # Timeline từng packet, chống lệch Frame Drift
│   │   ├── db_builder.py                               # SQLite runtime.sqlite, quản lý metadata & FTS5
│   │   ├── kaggle_runner.py                            # Điều phối chạy tự động trên Kaggle Dual GPU
│   │   ├── vector_extractor.py                         # [Mở rộng] Trích xuất vector nhúng SigLIP
│   │   ├── semantic_enricher.py                        # [Mở rộng] VLM Dense Video Captioning
│   │   ├── asr_transcriber.py                          # [Mở rộng] Whisper Speech-to-Text
│   │   └── vietnamese_cultural_lexicon.py              # [Mở rộng] Từ điển văn hóa bản địa
│   ├── scripts/steps/                                  # 7 Step Tests độc lập với dữ liệu thật
│   └── notebooks/                                      # Notebook chạy trên Kaggle / Colab
│
└── models/                                             # Quản lý định danh các mô hình AI
    ├── model_registry.py                               # Registry danh mục toàn bộ mô hình
    ├── vision_embedding_loader.py                      # Loader SigLIP / ViSigLIP
    ├── yolo_detector_loader.py                         # Loader YOLOv8 / YOLO-World
    └── ocr_asr_loaders.py                              # Loader PaddleOCR / Whisper
```

---

## 4. Hướng Dẫn Commit & Push Lên Nhánh `system1-kaggle-pipeline`

Để đóng gói toàn bộ mã nguồn và tài liệu lên đúng nhánh `system1-kaggle-pipeline`:

```bash
# 1. Chuyển sang hoặc tạo nhánh system1-kaggle-pipeline
git checkout -b system1-kaggle-pipeline 2>nul || git checkout system1-kaggle-pipeline

# 2. Thêm toàn bộ các tệp và tài liệu vào staging
git add system1-kaggle-pipeline/
git add interactive-test-app/
git add models/
git add .agents/
git add start_interactive_test_app.bat
git add run_all_system1_step_tests.bat
git add CONVERSATION_README.md
git add KEYFRAME_EXTRACTION_AND_PROCESSING_REPORT.md
git add README.md

# 3. Tạo commit với thông điệp chuẩn hóa
git commit -m "feat(system1): finalize core keyframe extraction and timeline sync pipeline (100% tests pass)"

# 4. Đẩy mã nguồn lên remote repository nhánh system1-kaggle-pipeline
git push -u origin system1-kaggle-pipeline
```
