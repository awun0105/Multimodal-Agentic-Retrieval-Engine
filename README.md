# MULTIMODAL AGENTIC RETRIEVAL ENGINE & INGESTION PIPELINE (AIC 2026)

Hệ thống Tìm kiếm Truy xuất Video Đa Phương Thức Thông Minh (Multimodal Agentic Retrieval Engine) và Kênh Tiền Xử Lý Dữ Liệu Tự Động Quy Mô Lớn (Large-Scale Video Ingestion Pipeline) được thiết kế chuyên biệt phục vụ cuộc thi **AI Challenge (AIC) 2026**.

---

## 1. Kiến Trúc Tổng Thể Của Hệ Thống

Hệ thống được thiết kế theo mô hình **Hybrid Song Song Hai Luồng (Dual-Stream Execution)** kết hợp giữa sức mạnh tính toán cục bộ siêu tốc (Local Low-Latency) và trí tuệ nhân tạo đám mây (Cloud High-Accuracy):

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                        MULTIMODAL AGENTIC RETRIEVAL ENGINE (AIC 2026 ARCHITECTURE)                     │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                        │
│  [PHÂN HỆ 1: SYSTEM 1 - OFFLINE INGESTION PIPELINE] (Kaggle Dual T4 / TPU v3-8 / GPU Local)            │
│  ┌─────────────────────────┐   ┌─────────────────────────┐   ┌──────────────────────────────────────┐  │
│  │ 1. Video & Shot Ingest  │──►│ 2. Multimodal Enrichment│──►│ 3. Unified Artifact Packaging        │  │
│  │ - Histogram / TransNet  │   │ - YOLOv8 Small/Large Obj│   │ - SQLite FTS5 (unicode61 diacritics) │  │
│  │ - Adaptive Keyframes    │   │ - EasyOCR Lower-Thirds  │   │ - FAISS SQ8 Inner Product            │  │
│  │ - Laplacian Sharpness   │   │ - Shot Context Meaning  │   │ - Virtual Dedup Proxy (Violet Frame) │  │
│  │ - Sharpening Fallback   │   │ - ASR Whisper large-v3  │   │ - Multi-Badge Timeline Synchronization│ │
│  └─────────────────────────┘   └─────────────────────────┘   └──────────────────────────────────────┘  │
│                                                                                  │                     │
│                                           Tải về máy cục bộ (< 1.5GB)            ▼                     │
│  [PHÂN HỆ 2: SYSTEM 2 - INTERACTIVE RETRIEVAL COCKPIT & LIVE ENGINE] (Latency < 100ms)                 │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │ - Tab 1: Side-by-Side Timeline Comparator (Đối chiếu BTC vs System 1, Multi-Badge, Frame Cắt Nghĩa)│  │
│  │ - Tab 2: Result Persistence & Memory-Saving Hub (Thống kê toàn bộ video, xuất JSON/CSV nộp bài)   │  │
│  │ - Tab 3: Benchmark Step Harness (Khám phá và kiểm thử độc lập Step 1 đến Step 5)                 │  │
│  │ - Tab 4: Hybrid Visual Search & Video QA (Dense SigLIP + Sparse FTS5 BM25 + ASR Audio Timestamp) │  │
│  │ - Tab 5: Ingestion Parameter Studio (Tùy chỉnh toàn bộ tham số quét frame, ngưỡng cắt, lọc nét) │  │
│  └──────────────────────────────────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Bản Đồ Cấu Trúc Thư Mục & Ý Nghĩa Từng Tệp (Directory Structure & File Index)

```text
Multimodal-Agentic-Retrieval-Engine/
│
├── start_interactive_test_app.bat                      # File chạy 1-Click khởi động Giao diện Web Cockpit trên Windows
├── CONVERSATION_README.md                              # Sổ cái trung tâm ghi nhận toàn bộ tính năng và tiến độ phát triển
├── README.md                                           # Tài liệu tổng quan và hướng dẫn vận hành chính của dự án
│
├── interactive-test-app/                               # Phân Hệ Giao Diện Tương Tác & Kiểm Duyệt Trực Quan (Cockpit Studio)
│   ├── app.py                                          # Ứng dụng Gradio Web Cockpit hoàn chỉnh (5 Tabs tính năng, Multi-Badge)
│   ├── launcher.py                                     # Trình khởi chạy an toàn, tự động giải phóng port 7860 và mở trình duyệt
│   ├── README.md                                       # Hướng dẫn chi tiết sử dụng 5 Tab tính năng của giao diện
│   └── ERROR_PREVENTION_AND_EDGE_CASES_README.md       # Sổ tay phòng ngừa lỗi dữ liệu biên (NaN/None/Type Mismatch)
│
├── system1-kaggle-pipeline/                            # Phân Hệ Tiền Xử Lý Dữ Liệu Lớn (Kaggle & Local Ingestion Pipeline)
│   ├── SYSTEM_ARCHITECTURE_AND_PIPELINE_OVERVIEW.md    # Tài liệu tổng quan toàn diện về kiến trúc và 8 trường metadata chuẩn tắc
│   ├── RUN_AND_EXECUTION_GUIDE_README.md               # Cẩm nang hướng dẫn khởi chạy và phân tích tuần tự 6 bước xử lý
│   ├── KEYFRAME_PIPELINE_README.md                     # Tài liệu chuyên sâu về cơ chế lấy mẫu keyframe thích ứng
│   ├── EXECUTION_MILESTONES.md                         # Báo cáo các mốc tiến độ thực nghiệm định lượng
│   ├── requirements_kaggle.txt                         # Danh sách thư viện tối ưu hóa cho môi trường Kaggle / GPU
│   │
│   ├── configs/                                        # Thư mục chứa cấu hình hệ thống
│   │   └── pipeline_config.yaml                        # Cấu hình các tham số phân đoạn cú máy, ngưỡng lọc nét, mô hình AI
│   │
│   ├── notebooks/                                      # Jupyter Notebooks thực thi 1-Click trên Đám mây
│   │   ├── kaggle_master_pipeline.ipynb                # Chạy trích xuất toàn bộ trên Kaggle Dual T4 GPU / TPU v3-8
│   │   └── colab_drive_to_kaggle_uploader.ipynb        # Cầu nối đồng bộ dữ liệu từ Google Drive sang Kaggle
│   │
│   ├── plans/                                          # Thư mục quản trị kế hoạch và phân mảnh tác vụ Sub-Agent
│   │   └── KEYFRAME_ENHANCEMENT_PLAN_AND_SUBAGENT_TASKS.md # Kế hoạch chi tiết, phân vai 3 Agent và nhật ký thảo luận kỹ thuật
│   │
│   ├── src/                                            # Mã nguồn các module lõi của System 1
│   │   ├── timeline_synchronizer.py                    # Module đồng bộ timeline BTC-Self, Frame Cắt Nghĩa viền tím, Multi-Badge
│   │   ├── frame_timeline.py                           # Khởi tạo timeline khung hình chuẩn xác PTS seconds
│   │   ├── shot_detector.py                            # Thuật toán phát hiện ranh giới cú máy (Shot Boundary Detection)
│   │   ├── adaptive_keyframe.py                        # Lấy mẫu keyframe thích ứng và lọc độ nét Laplacian Variance
│   │   ├── asr_transcriber.py                          # Nhận diện giọng nói tiếng Việt (faster-whisper large-v3)
│   │   ├── ocr_extractor.py                            # Quét chữ quang học chân trang tin tức (EasyOCR)
│   │   ├── vector_extractor.py                         # Trích xuất vector SigLIP Base Patch16-224 (Multi-GPU / TPU)
│   │   ├── semantic_enricher.py                        # Bóc tách 6 thuộc tính câu hỏi KIS và phân loại bối cảnh
│   │   ├── db_builder.py                               # Đóng gói SQLite FTS5 (Unicode61) và chỉ mục FAISS SQ8
│   │   └── kaggle_runner.py                            # Trình điều phối chạy toàn bộ pipeline tiền xử lý
│   │
│   ├── scripts/                                        # Kịch bản kiểm thử độc lập và chạy benchmark
│   │   ├── steps/                                      # Bộ kiểm thử 5 bước độc lập chuẩn tắc (100% ALL PASS)
│   │   │   ├── test_step1_event_keyframes.py           # Bước 1: Kiểm thử bắt sự kiện Enter/Exit và Crowd Suppression
│   │   │   ├── test_step2_video_ocr_dedup.py           # Bước 2: Kiểm thử khử trùng lặp chuỗi OCR chân trang
│   │   │   ├── test_step3_asr_timestamp_qa.py          # Bước 3: Kiểm thử tra cứu Video QA qua ASR timestamped FTS5
│   │   │   ├── test_step4_genre_classifier.py          # Bước 4: Kiểm thử phân loại thể loại video và sinh trọng số RRF
│   │   │   └── test_step5_timeline_merge_dedup.py      # Bước 5: Kiểm thử đồng bộ Timeline, Frame Cắt Nghĩa viền tím, Đa Tag
│   │   ├── run_10_videos_benchmark.py                  # Xử lý 10 video mẫu (5 đầu + 5 cuối) đối chứng với BTC
│   │   ├── run_raw_video_pipeline_test.py              # Xử lý toàn bộ video thô MP4 và cắt cú máy
│   │   ├── run_all_step_tests.py                       # Điều phối chạy toàn bộ các bài kiểm thử
│   │   └── README.md                                   # Hướng dẫn chi tiết từng script kiểm thử
│   │
│   └── test_output/                                    # Thư mục lưu trữ kết quả thực nghiệm
│       ├── side_by_side_benchmark/                     # Dữ liệu 10 video mẫu đối chứng phục vụ Studio
│       ├── extracted_keyframes/                        # Ảnh Keyframe HD (.jpg) cắt trực tiếp từ video gốc
│       ├── extracted_thumbnails/                       # Ảnh Thumbnail WebP (.webp) siêu nhẹ nén bộ nhớ
│       ├── unified_multimodal_dataset.json             # Bộ dữ liệu hợp nhất định dạng JSON
│       ├── unified_multimodal_dataset.csv              # Bộ dữ liệu hợp nhất định dạng CSV
│       └── shots_summary.csv                           # Bảng tổng hợp chi tiết toàn bộ cú máy
│
├── data_sample/                                        # Gói dữ liệu mẫu từ Ban Tổ Chức (BTC) phục vụ đối chứng
│   ├── Videos_L21_a.zip                                # 29 video MP4 gốc (3.2 GB)
│   ├── Keyframes_L21.zip                               # 7,829 ảnh keyframe của BTC (1.38 GB)
│   ├── clip-features-32-aic25-b1.zip                   # Ma trận vector CLIP 512D của 873 video
│   ├── map-keyframes-aic25-b1.zip                      # File CSV ánh xạ frame index và PTS seconds
│   ├── media-info-aic25-b1.zip                         # File JSON tiêu đề, kênh, link YouTube gốc
│   └── objects-aic25-b1.zip                            # File JSON danh sách vật thể AI phát hiện
│
└── .agents/                                            # Hệ thống luật, ngữ cảnh và nhật ký bàn giao của AI Agent
    ├── AGENTS.md                                       # Quy định cốt lõi của Agent (Nghiêm cấm emoji, dữ liệu chuẩn tắc)
    ├── rules/                                          # Các quy tắc phát triển của User (Rule 1-14)
    ├── notes/                                          # Sổ tay kỹ thuật và nhật ký chuyển giao bối cảnh (handover_log.md)
    └── context/                                        # Tổng quan kiến trúc và tiến độ dự án
```

---

## 3. Hướng Dẫn Khởi Động & Vận Hành (Quickstart & Execution)

### 3.1. Khởi Chạy Giao Diện Web Cockpit 1-Click (Khuyên Dùng Trên Windows)
Nhấp đúp chuột vào tệp:
👉 **[start_interactive_test_app.bat](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/start_interactive_test_app.bat)**

- Hệ thống sẽ tự động kiểm tra môi trường Python, giải phóng cổng `7860` nếu đang bị chiếm dụng và mở giao diện Web tại địa chỉ: **`http://127.0.0.1:7860`**.
- *Hoặc chạy thủ công qua Terminal:*
  ```powershell
  python interactive-test-app/launcher.py
  ```

---

### 3.2. Khởi Chạy Toàn Bộ Tiền Xử Lý Trên Kaggle (GPU / TPU)
1. Mở notebook: [system1-kaggle-pipeline/notebooks/kaggle_master_pipeline.ipynb](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/notebooks/kaggle_master_pipeline.ipynb).
2. Chọn accelerator phần cứng: **GPU T4 x 2** hoặc **TPU VM v3-8**.
3. Nhấp `Run All`. Toàn bộ dữ liệu kết quả sẽ được xử lý song song và đóng gói tự động vào `/kaggle/working/unified_output/`.

---

### 3.3. Chạy Kiểm Thử Độc Lập Các Bước (Unit Test Suites)
Chạy toàn bộ 5 bài kiểm thử độc lập trên dữ liệu thực tế bằng lệnh PowerShell:
```powershell
# Chạy toàn bộ 5 bài kiểm thử Step 1 đến Step 5
python system1-kaggle-pipeline/scripts/steps/test_step1_event_keyframes.py
python system1-kaggle-pipeline/scripts/steps/test_step2_video_ocr_dedup.py
python system1-kaggle-pipeline/scripts/steps/test_step3_asr_timestamp_qa.py
python system1-kaggle-pipeline/scripts/steps/test_step4_genre_classifier.py
python system1-kaggle-pipeline/scripts/steps/test_step5_timeline_merge_dedup.py
```

---

## 4. Thứ Tự Tuần Tự 6 Bước Xử Lý Dữ Liệu Lõi

```text
[Video Thô .MP4] 
   │
   ├─► BƯỚC 1: Phân đoạn Cú Máy & Lấy Mẫu Keyframe Thích Ứng (Shot Sampling)
   │   - Histogram HSV 320x180, bắt cú máy nhanh 0.4s - 3.0s, lọc độ nét Laplacian >= 35.0.
   │   - Cứu ảnh mờ qua Unsharp Masking (Sharpening Fallback) nếu cả cú máy đều mờ.
   │
   ├─► BƯỚC 2: Nhận Diện Đa Vật Thể (YOLO) & Bóc Tách OCR Chân Trang
   │   - YOLOv8 (conf=0.15, imgsz=640) bắt cả vật thể nhỏ/lớn, dịch >80 lớp COCO sang tiếng Việt.
   │   - EasyOCR tiếng Việt vùng chân trang (y > 0.65), khử trùng lặp Jaccard >= 0.85.
   │
   ├─► BƯỚC 3: Phân Tích Màu Sắc, Bối Cảnh & Ngữ Cảnh Toàn Cú Máy
   │   - Nét chữ Sobel, màu chủ đạo HSV, nhận diện bối cảnh môi trường.
   │   - Suy đoán ý nghĩa toàn cú máy: [Hoạt động] | Từ khóa: [kw1, kw2].
   │   - Bóc tách faster-whisper large-v3 có timestamp cho Video QA.
   │
   ├─► BƯỚC 4: Khử Trùng Lặp Cửa Sổ Trượt & Phân Loại Trực Quan
   │   - Cửa sổ trượt 3 frame, đo tương quan thị giác kết hợp Shot Continuity Curve.
   │   - Đánh dấu Đề Xuất Lọc Bỏ viền đỏ (#ff5555) kèm lý do chi tiết.
   │
   ├─► BƯỚC 5: Hợp Nhất Trục Thời Gian Chung Với BTC & Kích Hoạt Frame Cắt Nghĩa
   │   - Gộp mốc thời gian trùng (|Δt| <= 0.05s) kế thừa mã nộp bài BTC.
   │   - Kích hoạt Frame Cắt Nghĩa viền tím Neon (#bd93f9) + Δt (Zero Disk Waste).
   │   - Thẻ [BTC-xử lý] cho frame BTC đơn sắc hoặc mật độ thông tin thấp.
   │
   └─► BƯỚC 6: Đóng Gói Chỉ Mục Tìm Kiếm & Xuất Bộ Dữ Liệu Hợp Nhất
       - FAISS Index SQ8 (SigLIP Base 768D Inner Product).
       - SQLite FTS5 (Unicode61) bảng text_fts và asr_fts.
       - Xuất bản unified_multimodal_dataset.json và .csv.
```

---

## 5. Tổng Kết Kỹ Thuật & Các Hướng Đã Xử Lý Thành Công

Trong quá trình phát triển, các thách thức kỹ thuật phức tạp đã được phân tích và giải quyết triệt để:

1. **Cơ Chế Hiển Thị Đa Tag Phân Loại (Multi-Badge Display):**
   - Thay thế việc chọn 1 tag duy nhất bằng cơ chế gom danh sách động, cho phép hiển thị đồng thời nhiều tag: `[Frame Cắt Nghĩa +Δt]`, `[Đã Làm Nét - Fallback]`, `[Chuyển Cảnh / Tiêu Đề]`, `[Đề Xuất Lọc Bỏ - ...]`, `[BTC-xử lý: ...]`.
   - Thứ tự ưu tiên màu viền ngoài: **Đỏ (Lọc bỏ / BTC thấp)** > **Tím Neon (Cắt nghĩa)** > **Vàng Cam (Làm nét)** > **Xanh Cyan (BTC)** > **Xanh Lá (System 1)**.

2. **Ảo Hóa Frame Cắt Nghĩa (Virtual Reference Proxy - Viền Tím `#bd93f9`):**
   - Thay vì nhân bản ảnh thừa, hệ thống giữ lại khung hình Anchor đại diện và tạo bản ghi ảo mang thông tin độ lệch thời gian $\Delta t$ (`+1.2s`), giúp mắt người bao quát toàn bộ cú máy mà không tốn dung lượng đĩa (Zero Disk Waste).

3. **Nhận Diện & Đếm Vật Thể Nhỏ (Small Object Detection):**
   - Hạ ngưỡng YOLO xuống `conf = 0.15`, chạy độ phân giải cao `imgsz = 640`, mở rộng từ điển dịch thuật > 80 lớp COCO sang tiếng Việt (bánh mì, chó, mèo, cốc, đĩa, thìa, ghế, cờ, micro...) và đếm chính xác tần suất xuất hiện.

4. **Cơ Chế Cứu Ảnh Mờ (Sharpening Fallback via Unsharp Masking):**
   - Khi một cú máy ngắn bị mờ toàn bộ do chuyển động nhanh, hệ thống không xóa bỏ mà giữ lại frame tốt nhất và làm nét qua bộ lọc Unsharp Masking, gán tag `[Đã Làm Nét - Fallback]` (Viền Vàng Cam `#ebcb8b`).

5. **Phát Hiện Frame Ban Tổ Chức Cần Xử Lý (`[BTC-xử lý]`):**
   - Tự động phát hiện các frame BTC có mật độ thông tin thấp (ảnh đơn sắc, màn hình tối/sáng phẳng, Laplacian $< 25.0$) để cảnh báo bằng viền đỏ/cam và gắn badge `[BTC-xử lý: Mật độ thông tin thấp / Ảnh đơn sắc]`.

6. **Bóc Tách & Khử Trùng Lặp Chữ OCR Chân Trang:**
   - Tập trung vùng chân trang tin tức ($y > 0.65$), khử trùng lặp qua chỉ số tương đồng Jaccard $\ge 0.85$, giảm $>55\%$ chuỗi thừa mà vẫn giữ nguyên vẹn nội dung bản tin.

7. **Truy Vấn Video QA Qua ASR Timestamped FTS5:**
   - Tích hợp lời thoại bóc tách từ `faster-whisper large-v3` vào cơ sở dữ liệu SQLite FTS5 có timestamp, cho phép tra cứu câu hỏi Video QA trong thời gian $< 2\text{ms}$.

8. **Kiến Trúc Phòng Thủ Toàn Diện Chống Lỗi Dữ Liệu Biên:**
   - Xây dựng bộ tiện ích an toàn (`safe_extract_object_keys`, `clean_text_field`, `safe_float`) triệt tiêu 100% rủi ro crash do dữ liệu `NaN`, `None`, `null` hoặc chuỗi rác khi đọc từ file CSV.

---

## 6. Minh Chứng Thực Nghiệm Định Lượng (Empirical Proofs)

| Phân Hệ Kiểm Thử | Tệp Thực Thi | Kết Quả Định Lượng | Trạng Thái |
| :--- | :--- | :--- | :--- |
| **Step 1: Event Keyframes** | [test_step1_event_keyframes.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/steps/test_step1_event_keyframes.py) | Bắt trúng mốc Enter/Exit, Crowd Suppression $\le 5$ người. | **100% PASS** |
| **Step 2: OCR Dedup** | [test_step2_video_ocr_dedup.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/steps/test_step2_video_ocr_dedup.py) | Giảm $>55\%$ chuỗi trùng lặp, phân vùng chân trang $y > 0.65$. | **100% PASS** |
| **Step 3: Video QA ASR** | [test_step3_asr_timestamp_qa.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/steps/test_step3_asr_timestamp_qa.py) | 4/4 câu hỏi Video QA tra cứu chính xác mốc giây $< 2\text{ms}$. | **100% PASS** |
| **Step 4: Genre Classifier**| [test_step4_genre_classifier.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/steps/test_step4_genre_classifier.py) | 9/9 thể loại video phân loại chuẩn xác, tự động sinh trọng số RRF. | **100% PASS** |
| **Step 5: Timeline Dedup** | [test_step5_timeline_merge_dedup.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/steps/test_step5_timeline_merge_dedup.py) | 8/8 test cases: gộp $|\Delta t| \le 0.05\text{s}$, đếm vật thể, Frame Cắt Nghĩa viền tím, Multi-Badge, tag BTC-xử lý, chống crash NaN. | **100% PASS** |
| **Thực Nghiệm Video L21_V001**| [scratch/test_dedup_live.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/scratch/test_dedup_live.py) | Kích hoạt chuẩn xác 5 Frame Cắt Nghĩa viền tím Neon tại 2.6s, 8.1s, 11.8s, 24.0s, 58.8s. | **100% PASS** |

---

## 7. Trung Tâm Tài Liệu Tham Chiếu Chuyên Sâu (Documentation Hub)

- [Tổng Quan Kiến Trúc Hệ Thống (System Overview)](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/SYSTEM_ARCHITECTURE_AND_PIPELINE_OVERVIEW.md)
- [Cẩm Nang Hướng Dẫn Khởi Chạy & Thứ Tự Các Bước (Run Guide)](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/RUN_AND_EXECUTION_GUIDE_README.md)
- [Sổ Tay Phòng Ngừa Lỗi & Dữ Liệu Biên (Error Prevention)](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/interactive-test-app/ERROR_PREVENTION_AND_EDGE_CASES_README.md)
- [Kế Hoạch Nâng Cấp Keyframe & Phân Nhiệm Sub-Agent](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/plans/KEYFRAME_ENHANCEMENT_PLAN_AND_SUBAGENT_TASKS.md)
- [Hướng Dẫn Sử Dụng Giao Diện Cockpit Studio](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/interactive-test-app/README.md)
- [Sổ Cái Trung Tâm Ghi Nhận Tính Năng (Conversation README)](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/CONVERSATION_README.md)
- [Nhật Ký Chuyển Giao Bối Cảnh Giữa Các Agent (Handover Log)](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/.agents/notes/handover_log.md)

---

## 8. Bàn Giao Kế Hoạch & Định Hướng Phát Triển Tiếp Theo (Future Roadmap)

1. **Hoàn Thiện Phân Hệ System 2 (Live Interactive Retrieval Engine):**
   - Tích hợp Translation API (Google / DeepL / LLM) dịch tự động câu truy vấn tiếng Việt sang tiếng Anh trước khi đưa vào mô hình Embedding.
   - Kết nối cơ chế tìm kiếm lai Hybrid RRF: SigLIP Vector Search + SQLite FTS5 Text Search + ASR Video QA.
2. **Kích Hoạt Luồng Phối Hợp Hybrid Cloud API (Stream B):**
   - Kết nối Gemini 3.1 Pro / GPT-4o / Claude API chạy song song để làm giàu prompt truy vấn nâng cao và re-rank Top 100 kết quả trong thời gian $< 1.5\text{s}$.
3. **Bộ Giải Chuỗi Hành Động TRAKE (Sequence Solver via Dynamic Programming):**
   - Xây dựng thuật toán Quy hoạch động tìm kiếm chuỗi 2-3 sự kiện diễn ra tuần tự theo trật tự thời gian tăng ngặt trong cùng một video.
