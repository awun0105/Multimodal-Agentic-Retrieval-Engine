# Ma Trận Phân Giao Tác Vụ & Khung Quản Trị Sub-Agents System 1 (Rule 11 Compliance)

Tài liệu này phân mảnh toàn bộ kiến trúc System 1 thành 4 module độc lập phục vụ cho việc phát triển song song, giao việc cho các mô hình AI khác nhau (Claude 3.5 Sonnet, GPT-4o, Gemini 3.1 Pro) và kiểm duyệt tự động thông qua mô hình quản trị 3 vai trò.

---

## 1. Mô Hình Quản Trị Ba Vai Trò (Three-Role Agent Framework)

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                  1. ORCHESTRATION AGENT (Agent Quản Lý)                       │
│ - Chịu trách nhiệm: Điều phối dữ liệu, liên kết các module, quản lý pipeline │
│   chính (kaggle_runner.py), xử lý ngoại lệ (fault-tolerance), và tổng hợp DB │
├──────────────────────────────────────┬───────────────────────────────────────┤
│                                      │                                       │
│                  ▼                   │                   ▼                   │
│ ┌──────────────────────────────────┐ │ ┌───────────────────────────────────┐ │
│ │ 2. EXECUTION AGENT (Agent Thực Thi│ │ │ 3. VALIDATION AGENT (Kiểm Duyệt)  │ │
│ │ - Viết code tối ưu thuật toán    │ │ │ - Chạy test harness độc lập       │ │
│ │ - Đảm bảo ràng buộc GPU/RAM      │ │ │ - Thẩm định Data Contracts JSON   │ │
│ │ - Thực thi các module Phase 00-03│ │ │ - Đánh giá độ sắc nét, L2 Norm    │ │
│ └──────────────────────────────────┘ │ └───────────────────────────────────┘ │
└──────────────────────────────────────┴───────────────────────────────────────┘
```

1. **Agent Quản Lý Phân Mục (Orchestration Agent):**
   - Điều phối luồng dữ liệu giữa các module.
   - Quản lý tệp cấu hình trung tâm [pipeline_config.yaml](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/configs/pipeline_config.yaml) và script runner [kaggle_runner.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/kaggle_runner.py).
   - Đảm bảo gói phát hành cuối cùng `release_artifacts.zip` chứa đầy đủ các bảng dữ liệu theo chuẩn.

2. **Agent Thực Hiện (Execution Agent):**
   - Tập trung phát triển, tối ưu mã nguồn cho từng module chuyên biệt trong `system1-kaggle-pipeline/src/`.
   - Đáp ứng các ràng buộc về bộ nhớ và phần cứng (FP16 trên GPU, DataParallel, XLA trên TPU).

3. **Agent Kiểm Duyệt (Validation Agent):**
   - Thực thi các kịch bản kiểm thử độc lập qua [validate_subagent_pipeline.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/validate_subagent_pipeline.py).
   - Thẩm định tính đúng đắn của hợp đồng dữ liệu trước khi cho phép tích hợp vào pipeline chính.

---

## 2. Ma Trận Phân Giao Tác Vụ Chi Tiết (Task Delegation Matrix)

### Module 1: Chuẩn Hóa Khung Hình & Phân Tách Cú Máy (Phase 00 + Phase 01 Visual)

- **Mục tiêu Module:** Nhận diện toàn bộ khung hình video qua Packet Counting và phân tách video thành danh sách các cú máy độc lập, loại bỏ frame mờ.
- **Đầu vào (Inputs):** Tệp video MP4/MKV thô (`raw_videos/*.mp4`).
- **Đầu ra (Outputs):** 
  - Bảng timeline: `frame_timeline/{video_id}.parquet` (Cột: `frame_id`, `pts_time_sec`, `fps`).
  - Danh sách shots: `List[Dict]` gồm `shot_id`, `start_frame`, `end_frame`, `duration_sec`.
  - Ảnh keyframes chất lượng cao (`.jpg`) và ảnh thu nhỏ WebP 128x128.
- **Hợp đồng dữ liệu (JSON/Dict Contract):**
  ```json
  {
    "video_id": "L21_V001",
    "keyframe_id": "L21_V001_000125",
    "shot_id": 3,
    "frame_id": 125,
    "pts_time_sec": 5.00,
    "sharpness_laplacian": 548.88,
    "keyframe_path": "keyframes/L21_V001/000125.jpg",
    "thumbnail_path": "thumbnails/L21_V001/000125.webp"
  }
  ```
- **Ràng buộc hiệu năng & Latency:**
  - Tốc độ giải mã $\ge 150\text{ fps}$ trên CPU/GPU.
  - Ngưỡng phương sai Laplacian $\ge 40.0$.
- **Kế hoạch kiểm thử độc lập:** Chạy `benchmark_runner.py --mode raw_video --video L21_V001 --frames 500`.

---

### Module 2: Trích Xuất Vector Nhúng Đa Phương Thức (Phase 02 Vector)

- **Mục tiêu Module:** Trích xuất vector biểu diễn ngữ nghĩa cho toàn bộ keyframes bằng mô hình SigLIP Base.
- **Đầu vào (Inputs):** Danh sách đường dẫn ảnh keyframe (`List[str]`).
- **Đầu ra (Outputs):** Ma trận vector $\text{NumPy Array } (N, 768)$ kiểu `float32` hoặc `float16`.
- **Hợp đồng dữ liệu (JSON/Dict Contract):**
  ```json
  {
    "model_name": "google/siglip-base-patch16-224",
    "embedding_dim": 768,
    "normalized_l2": true,
    "vector_map": [
      {"vector_id": 0, "keyframe_id": "L21_V001_000125"},
      {"vector_id": 1, "keyframe_id": "L21_V001_000280"}
    ]
  }
  ```
- **Ràng buộc hiệu năng & Latency:**
  - Mọi vector bắt buộc phải chuẩn hóa $L_2\text{-Norm} = 1.0 \pm 1e-5$.
  - Tốc độ xử lý $\ge 100\text{ images/sec}$ trên GPU T4 (FP16, Batch size 64).
- **Kế hoạch kiểm thử độc lập:** Chạy `python system1-kaggle-pipeline/scripts/steps/step2_embeddings.py`.

---

### Module 3: Bóc Tách Giọng Nói, Chữ Viết & Theo Dõi Vật Thể (Phase 02 Multimodal)

- **Mục tiêu Module:** Bóc tách toàn bộ âm thanh tiếng Việt, nhận diện chữ chạy chân trang tin tức và theo dõi liên tục định danh vật thể trên luồng video.
- **Đầu vào (Inputs):** Tệp video MP4 và các ảnh keyframe.
- **Đầu ra (Outputs):**
  - Danh sách phụ đề ASR (`List[Dict]` có `start_sec`, `end_sec`, `text`).
  - Danh sách chữ OCR (`List[Dict]` có `text`, `confidence`, `is_lower_third`).
  - Danh sách vật thể theo dõi YOLOv8 (`active_tracks` kèm `first_seen`, `last_seen`, `class`).
- **Hợp đồng dữ liệu (JSON/Dict Contract):**
  ```json
  {
    "keyframe_id": "L21_V001_000125",
    "ocr_texts": ["BAN TIN 60 GIAY", "TP HO CHI MINH"],
    "is_lower_third": 1,
    "unique_objects": ["2 persons", "1 car"],
    "detected_objects_detail": "person (0.85), car (0.92)",
    "asr_transcript": "Hom nay tai trung tam thanh pho"
  }
  ```
- **Ràng buộc hiệu năng & Latency:**
  - ASR chạy `faster-whisper large-v3` ở chế độ FP16 / INT8 (tốc độ $\ge 5\text{x real-time}$).
  - EasyOCR giới hạn vùng chân trang $y > 0.65$ cho tin tức để tiết kiệm 60% thời gian tính toán.
- **Kế hoạch kiểm thử độc lập:** Chạy `python system1-kaggle-pipeline/scripts/steps/step3_ocr.py`.

---

### Module 4: Đóng Gói Chỉ Mục Tìm Kiếm & Cơ Sở Dữ Liệu (Phase 03 Packaging)

- **Mục tiêu Module:** Hợp nhất toàn bộ metadata, văn bản và ma trận vector thành cơ sở dữ liệu SQLite FTS5 và chỉ mục FAISS SQ8.
- **Đầu vào (Inputs):** Danh sách dictionaries metadata từ Module 1, 2, 3.
- **Đầu ra (Outputs):**
  - Tệp `runtime.sqlite` chứa bảng ảo `text_documents_fts` (Tokenizer `unicode61 remove_diacritics 2`).
  - Tệp `siglip.faiss` lượng tử hóa 8-bit (Metric `METRIC_INNER_PRODUCT`).
  - Tệp nén `release_artifacts.zip` (< 1GB).
- **Ràng buộc hiệu năng & Latency:**
  - Dung lượng RAM khi nạp chỉ mục FAISS SQ8 $\le 500\text{MB}$ cho 100,000 vectors.
  - Tốc độ truy vấn từ khóa trên SQLite FTS5 $\le 10\text{ms}$.
- **Kế hoạch kiểm thử độc lập:** Chạy `python system1-kaggle-pipeline/scripts/steps/step4_db_search.py`.

---

## 3. Bộ Quy Tắc Kiểm Nghiệm Của Validation Sub-Agent (Acceptance Rules)

Trước khi bàn giao kết quả của bất kỳ module nào cho User, **Validation Sub-Agent** bắt buộc phải chạy file kiểm thử tự động và xác nhận đạt các tiêu chí sau:

- [ ] **Tiêu chuẩn 1 (Data Contract Integrity):** Tất cả các trường bắt buộc (`video_id`, `keyframe_id`, `frame_id`, `pts_time_sec`) không được mang giá trị `null` hoặc `undefined`.
- [ ] **Tiêu chuẩn 2 (Laplacian Variance):** 100% keyframes được chọn phải có $\text{Var}(\nabla^2 I) \ge 40.0$.
- [ ] **Tiêu chuẩn 3 (SigLIP Vector L2 Norm):** Ma trận vector nhúng phải có chuẩn độ dài $\|v\|_2 \in [0.9999, 1.0001]$.
- [ ] **Tiêu chuẩn 4 (SQLite FTS5 Tokenizer):** Bảng `text_documents_fts` bắt buộc phải sử dụng tokenizer `unicode61 remove_diacritics 2` để đảm bảo tìm kiếm chính xác cả tiếng Việt có dấu và không dấu.
- [ ] **Tiêu chuẩn 5 (Zero Disk Waste):** Tổng dung lượng các tệp phát hành trong thư mục xuất bản không vượt quá 2GB.
