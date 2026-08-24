<!-- 
================================================================================
AGENT CONTEXT & PROTOCOL HEADER (DÀNH CHO CÁC AI AGENT KẾ NHIỆM)
- Tên tài liệu: system1-kaggle-pipeline/README.md (TẦNG 1: Master Handbook)
- Vai trò trong hệ thống: Cẩm nang kỹ thuật tổng thể, định nghĩa kiến trúc 4 Phase, hợp đồng dữ liệu và bản đồ liên kết toàn hệ thống.
- Ràng buộc quy tắc (Rules Compliance):
  * Rule 1: Giải thích rõ ràng mục tiêu ở đầu mỗi mục lớn.
  * Rule 10: Nguyên tắc Append-Only (không xóa/sửa luật và lịch sử cũ).
  * Rule 11: Mô hình Quản trị 3 vai trò và Hợp đồng dữ liệu JSON/Dict.
  * Rule 12: Đồng bộ hóa bắt buộc với CONVERSATION_README.md.
  * Rule 13: Chủ động đặt câu hỏi làm rõ và thảo luận đề xuất cải tiến tính năng.
  * Rule 14: Quản trị kế hoạch trong plans/ và ghi nhận nhật ký thảo luận phát sinh.
  * Tone Constraint: Tuyệt đối KHÔNG dùng emoji/icon ở bất kỳ đâu.
- Tệp liên kết thượng nguồn (Upstream): .agents/rules/user_rules.md, CONVERSATION_README.md
- Tệp liên kết hạ nguồn (Downstream): PIPELINE_FLOW_AND_VERIFICATION.md, KEYFRAME_PIPELINE_README.md, plans/
- Kịch bản kiểm thử tương ứng: python system1-kaggle-pipeline/scripts/validate_subagent_pipeline.py
================================================================================
-->

# Sổ Tay Kỹ Thuật System 1 Kaggle Pipeline: Kiến Trúc Tiền Xử Lý & Hướng Dẫn Triển Khai

Tài liệu này là cẩm nang kỹ thuật toàn diện về **System 1 Ingestion Pipeline** được thiết kế riêng cho môi trường **Kaggle Notebooks (GPU T4 kép & TPU v3-8)** và máy thi đấu cục bộ trong khuôn khổ cuộc thi HCMC AI Challenge (AIC 2026).

---

## 1. Tổng Quan & Sứ Mệnh Kỹ Thuật (System 1 Overview & Mission)

System 1 là nhà máy tiền xử lý dữ liệu ngoại tuyến (Offline Multimodal Data Factory). Hệ thống chuyển đổi video thô MP4 và siêu dữ liệu chưa chuẩn hóa thành các tệp chỉ mục tìm kiếm siêu nhẹ, sẵn sàng phục vụ trực tiếp cho System 2 / MVP Retrieval App.

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                SYSTEM 1 OFFLINE FACTORY                                │
├─────────────────────────┬────────────────────────────┬─────────────────────────────────┤
│ Dữ liệu đầu vào thô     │ Quy trình xử lý tự chủ     │ Gói phát hành cuối cùng         │
│ - Video MP4 (10GB - 2TB)│ - Packet Counting Timeline │ (release_artifacts.zip < 1GB)   │
│ - Metadata thô từ BTC   │ - Shot Boundary Detection  │ - runtime.sqlite (FTS5 Unicode) │
│ - Objects phát hiện sẵn │ - Adaptive Keyframe & Blur │ - siglip.faiss (SQ8 Index)      │
│                         │ - faster-whisper Large-V3  │ - READY.json & manifest.json    │
│                         │ - EasyOCR / Vintern-1B     │ - Thumbnails WebP 128x128       │
│                         │ - SigLIP Base L2 Embedding │                                 │
│                         │ - YOLOv8 ByteTrack Dynamic │                                 │
└─────────────────────────┴────────────────────────────┴─────────────────────────────────┘
```

### 1.1. Bốn Hạn Chế Chí Mạng Của Dữ Liệu Ban Tổ Chức (BTC) & Giải Pháp Khắc Phục

| Hạn Chế Của Dữ Liệu BTC | Nguyên Nhân Gốc Rễ | Giải Pháp Của System 1 Pipeline |
| :--- | :--- | :--- |
| **1. Lệch số thứ tự khung hình (Frame ID Drift)** | BTC dùng công thức tính thời gian `pts_time * fps`, làm lệch 1-5 frame khi chấm điểm tự động. | Sử dụng **FFmpeg Packet Counting** đếm chính xác từng packet để lập bảng `frame_timeline/{video_id}.parquet`. |
| **2. Keyframe bị nhòe và bỏ sót hành động** | Lấy mẫu chu kỳ cố định không thích ứng theo chuyển động máy quay hay thời lượng cú máy. | Phát hiện cú máy bằng **TransNet V2** + Lấy mẫu đa dải (20%-50%-80%) + Bộ lọc độ sắc nét **Laplacian Variance $\ge 40.0$**. |
| **3. Mô hình Vector cũ (CLIP ViT-B/32 từ 2021)** | Hàm mất mát Softmax trên toàn batch gây bẫy nhầm màu sắc vật thể (áo đỏ cạnh xe xanh). | Chuyển sang **SigLIP Base (`google/siglip-base-patch16-224`)** dùng Sigmoid Loss độc lập + Chuẩn hóa $L_2 = 1.0$. |
| **4. Thiếu hụt thông tin đa phương thức** | Dữ liệu BTC không có bóc tách giọng nói, thiếu OCR chân trang tin tức, không có tracking vật thể. | Tích hợp **faster-whisper large-v3**, **OCR vùng chân trang (Lower Thirds)**, và **YOLOv8 ByteTrack**. |

### 1.2. Tối Ưu Chuyên Biệt Cho Các Thể Loại Video Tiếng Việt

- **Tin Tức / Thời Sự (60 Giây, VTV/HTV):** Tự động bóc tách chữ chạy chân trang (`is_lower_third = 1`) và phiên âm lời đọc phát thanh viên.
- **Phỏng Vấn / Talkshow / Gameshow:** Gắn nhãn thời gian hội thoại theo mili-giây phục vụ câu hỏi Video Q&A ("Ai nói câu gì").
- **Video Dạy Nấu Ăn / Hướng Dẫn Kỹ Thuật:** Lấy mẫu thích ứng bắt trọn các khung hình cận cảnh nguyên liệu và thao tác.
- **Bài Giảng Trực Tuyến:** Phát hiện biến đổi nội dung slide và quét OCR toàn trang đưa vào SQLite FTS5.

---

## 2. Kiến Trúc 4 Tầng Chuẩn Hóa (Modular 4-Stage Architecture)

Pipeline được kế thừa và tinh gọn từ kiến trúc chuẩn của `main-dev/system1`:

```text
[Video Gốc MP4 + Metadata Thô]
               │
               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ TẦNG 1: CHUẨN HÓA KHUNG HÌNH & BÓC TÁCH ÂM THANH (PHASE 00)             │
│ - Module: frame_timeline.py                                             │
│ - FFmpeg Packet Counting: Khớp 1-1 từng khung hình thực tế              │
│ - Xuất bản: frame_timeline/{video_id}.parquet & trích xuất Audio 16kHz  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ TẦNG 2: PHÁT HIỆN CÚ MÁY & TRÍCH XUẤT KEYFRAME THÔNG MINH (PHASE 01)     │
│ - Modules: shot_detector.py, adaptive_keyframe.py, asr_transcriber.py   │
│ - Phân tách cú máy (Hard cuts & Dissolves) qua TransNet V2              │
│ - Lấy mẫu thích ứng 3 dải (20%, 50%, 80%) + Bộ lọc Laplacian Blur      │
│ - Sinh ảnh thu nhỏ WebP 128x128 phục vụ Lean Mode                       │
│ - Bóc tách lời thoại tiếng Việt qua faster-whisper Large-V3             │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ TẦNG 3: TRÍCH XUẤT VECTOR ĐA PHƯƠNG THỨC & NGỮ NGHĨA KIS (PHASE 02)     │
│ - Modules: vector_extractor.py, ocr_extractor.py, semantic_enricher.py  │
│            object_detector.py                                           │
│ - SigLIP Base (Patch16-224): Trích xuất vector 768D chuẩn hóa L2        │
│ - EasyOCR / Vintern-1B: Bóc tách chữ có dấu và gắn cờ is_lower_third    │
│ - YOLOv8 + ByteTrack: Theo dõi đối tượng động và đếm số lượng duy nhất  │
│ - Bóc tách 6 trường KIS: Màu sắc, Góc máy, Ánh sáng, Không gian, v.v.   │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ TẦNG 4: HỢP NHẤT DỮ LIỆU & ĐÓNG GÓI CHỈ MỤC TÌM KIẾM (PHASE 03)         │
│ - Module: db_builder.py                                                 │
│ - SQLite WAL Database: Bảng ảo text_documents_fts (FTS5 Unicode61)      │
│ - FAISS Index: Lượng tử hóa SQ8 (Scalar Quantizer 8-bit, Inner Product) │
│ - Xuất bản READY.json và nén release_artifacts.zip                      │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.1. Chi Tiết Từng Module Trong Thư Mục `src/`

1. **[frame_timeline.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/frame_timeline.py):** Đọc luồng gói tin video, tạo bảng DataFrame với các cột `frame_id`, `pts_time_sec`, `fps`. Đây là căn cứ thời gian duy nhất cho toàn hệ thống.
2. **[shot_detector.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/shot_detector.py):** Cắt video thành danh sách các cú máy (`shot_id`, `start_frame`, `end_frame`).
3. **[adaptive_keyframe.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/adaptive_keyframe.py):** Lấy mẫu keyframe thông minh theo độ dài cú máy. Áp dụng công thức phương sai Laplacian:
   $$\text{Var}(\nabla^2 I) = \frac{1}{N}\sum_{x,y} (\nabla^2 I(x,y) - \mu)^2 \ge 40.0$$
   Nếu frame ứng viên bị nhòe, tự động quét tìm khung hình nét nhất trong phạm vi $\pm 2$ frame lân cận.
4. **[asr_transcriber.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/asr_transcriber.py):** Sử dụng `faster-whisper large-v3` kèm bộ lọc VAD (`vad_filter=True`) và `initial_prompt` định hướng tin tức, thể thao tiếng Việt.
5. **[ocr_extractor.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/ocr_extractor.py):** Bóc tách chữ viết tiếng Việt, phân loại vùng chân trang tin tức ($y > 0.65$) và thiết lập cờ `is_lower_third`.
6. **[object_detector.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/object_detector.py):** Tích hợp mô hình `yolov8n.pt` và thuật toán `ByteTrack`, ghi nhận hành trình (`first_seen`, `last_seen`) của từng vật thể và thống kê số lượng duy nhất trong từng cú máy.
7. **[semantic_enricher.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/semantic_enricher.py):** Trích xuất 6 trường thuộc tính KIS chuyên sâu (màu sắc, góc máy, ánh sáng, bối cảnh, số lượng đồ vật, hành động).
8. **[vector_extractor.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/vector_extractor.py):** Trích xuất vector nhúng SigLIP Base theo batch trên GPU hoặc TPU, thực hiện chuẩn hóa vector $L_2\text{-Norm} = 1.0$.
9. **[db_builder.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/db_builder.py):** Xây dựng tệp SQLite FTS5 hỗ trợ tiếng Việt không dấu/có dấu (`unicode61 remove_diacritics 2`) và tạo chỉ mục `siglip.faiss` lượng tử hóa SQ8.
10. **[kaggle_runner.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/kaggle_runner.py):** Bộ điều phối toàn diện 5 bước, tự động quét video, gọi các module và đóng gói tệp nén phát hành.

---

## 3. Hợp Đồng Dữ Liệu & Quy Trình Tiêu Thụ Tinh Gọn (Data Contract & Runtime Integration)

Sau khi hoàn tất quá trình xử lý, System 1 xuất bản gói dữ liệu chuẩn tắc `release_artifacts.zip` hoặc thư mục cấu trúc tương thích với `monolith-mvp-app`:

```text
data/aic26-b1-v1/
├── index/
│   ├── siglip.faiss          # Chỉ mục vector FAISS SQ8 (METRIC_INNER_PRODUCT)
│   ├── embeddings.f16.npy    # Ma trận vector nhúng dự phòng (Memory-Mapped)
│   └── faiss.meta.json       # Metadata liên kết vector_id <-> keyframe_id
├── metadata/
│   ├── runtime.sqlite        # Cơ sở dữ liệu SQLite FTS5 (Toàn bộ metadata, ASR, OCR, KIS)
│   ├── videos.parquet        # Danh mục thông tin video gốc
│   └── keyframes.parquet     # Danh mục keyframe chi tiết
├── keyframes/                # Thư mục ảnh keyframe (hoặc tệp keyframes.blob)
├── thumbnails/               # Ảnh WebP thu nhỏ 128x128 (Lean Mode)
├── manifest.json             # Bản kê checksum và thông số mô hình
└── READY.json                # Cờ xác nhận dữ liệu đã sẵn sàng nạp
```

### 3.1. Kỹ Thuật Đọc Ảo `VirtualBlobReader` (Chiến Thuật Zero Disk Waste)
- **Vấn đề trên Kaggle:** Dung lượng ổ cứng ghi `/kaggle/working/` bị giới hạn nghiêm ngặt ở mức 20GB. Nếu giải nén hàng trăm nghìn tệp ảnh tĩnh `.jpg` ra đĩa, hệ thống sẽ bị tràn bộ nhớ đĩa và mất hàng giờ cho thao tác inode indexing.
- **Giải pháp:**
  - Gom toàn bộ keyframes thành một tệp nhị phân duy nhất `keyframes.blob` bằng chuẩn `zipfile.ZIP_STORED` (không nén thuật toán, chi phí giải nén CPU bằng 0).
  - System 2 / MVP App sử dụng `VirtualBlobReader` để trích xuất byte ảnh trực tiếp vào RAM theo yêu cầu:
    ```python
    raw_bytes = blob_zip.read(f"{video_id}/{frame_id:06d}.jpg")
    image = Image.open(io.BytesIO(raw_bytes))
    ```

### 3.2. Chế Độ Vận Hành Kép (Lean Mode vs Rich Mode)
- **Lean Mode (Máy yếu / Môi trường thi trực tiếp):** Ứng dụng chỉ tải `runtime.sqlite` (< 500MB) và `siglip.faiss` SQ8 (< 300MB) cùng ảnh WebP thu nhỏ. Toàn bộ hệ thống khởi động trong 3 giây và tiêu tốn dưới 2GB RAM.
- **Rich Mode (Máy trạm / Đầy đủ hình ảnh):** Nạp thêm đường dẫn video MP4 gốc để mở trình phát video và xem dòng thời gian chi tiết.

---

## 4. Chiến Lược Phần Cứng Đám Mây & Băng Thông Cao (Cloud Scaling)

Để xử lý tập dữ liệu từ hàng chục đến hàng trăm GB mà không làm nghẽn máy cá nhân, toàn bộ quy trình được thực hiện trên hạ tầng đám mây:

```text
┌───────────────────────────┐      Băng thông nội bộ Google      ┌───────────────────────────┐
│       Google Drive        │ ─────────────────────────────────► │       Google Colab        │
│ (Chứa các file zip video) │        (~200MB/s - 1GB/s)          │ (colab_drive_to_kaggle)   │
└───────────────────────────┘                                    └─────────────┬─────────────┘
                                                                               │
                                                                               │ Kaggle API Upload
                                                                               ▼
┌───────────────────────────┐      Tải Artifacts Siêu Nhẹ        ┌───────────────────────────┐
│     Máy Thi Đấu Cục Bộ    │ ◄───────────────────────────────── │    Kaggle Master Runner   │
│ (Nạp .sqlite & .faiss)    │         (< 500MB - 1GB)            │ (Dual T4 GPU / TPU v3-8)  │
└───────────────────────────┘                                    └───────────────────────────┘
```

### 4.1. Phân Bổ Phần Cứng & Nhân Đôi Hạn Mức (50 Giờ / Tuần)

| Nền Tảng | Phần Cứng | Hạn Mức Miễn Phí | Phân Bổ Tác Vụ Tối Ưu |
| :--- | :--- | :--- | :--- |
| **Google Colab** | CPU / T4 GPU | 4 - 12h / session | **Data Staging:** Mount Drive, giải nén trên NVMe cục bộ, đóng gói `.blob`, đẩy sang Kaggle qua API. |
| **Kaggle GPU** | Dual T4 (16GB x 2) | **30 Giờ / Tuần** | **CUDA Pipeline:** TransNet V2, `faster-whisper large-v3`, EasyOCR, YOLOv8 ByteTrack. |
| **Kaggle TPU** | TPU v3-8 (128GB HBM) | **20 Giờ / Tuần** (Độc lập) | **Massive Vector Embedding:** Trích xuất ma trận vector SigLIP Base với batch size cực lớn (2048+). |

### 4.2. Quy Tắc Tối Ưu XLA Khi Chạy Trên TPU v3-8
- **Tránh Dynamic Tensor Shapes:** Luôn cắt hoặc pad ảnh về kích thước chuẩn `(224, 224)` và cố định `batch_size = 256` trên mỗi core để tránh việc XLA phải biên dịch lại đồ thị tính toán.
- **Phân tách trách nhiệm:** Không chạy thư viện CUDA (`faster-whisper`, `faiss-gpu`) trên nhân TPU; chỉ sử dụng TPU cho các mô hình PyTorch chuẩn (`SigLIP`, `CLIP`, `VLM`).

---

## 5. Sổ Tay Kỹ Sư: Bảng Tra Cứu Sự Cố Thực Chiến (Handover Knowledge Base)

| STT | Vấn Đề Thực Tế | Nguyên Nhân Gốc Rễ | Giải Pháp Kỹ Thuật Đã Kiểm Chứng | Module Mã Nguồn Phụ Trách |
| :--- | :--- | :--- | :--- | :--- |
| **1** | **Lệch số frame khi nộp bài** | Dùng ước lượng `pts_time * fps`. | Đếm chính xác packet qua FFmpeg, lập bảng timeline. | [src/frame_timeline.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/frame_timeline.py) |
| **2** | **Keyframe bị nhòe chuyển động** | Lấy mẫu chu kỳ thời gian cố định. | Bộ lọc phương sai Laplacian $\ge 40.0$, quét dò $\pm 2$ frame nét nhất. | [src/adaptive_keyframe.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/adaptive_keyframe.py) |
| **3** | **Bẫy nhầm màu sắc trong KIS** | CLIP Softmax loss trên toàn batch. | SigLIP Base Sigmoid loss độc lập + Chuẩn hóa $L_2 = 1.0$. | [src/vector_extractor.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/vector_extractor.py) |
| **4** | **Câu hỏi KIS chi tiết (Góc máy, Ánh sáng)** | Vector toàn cảnh làm mờ chi tiết nhỏ. | Bóc tách 6 trường KIS đưa vào SQLite FTS5 (Hybrid Search RRF). | [src/semantic_enricher.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/semantic_enricher.py) |
| **5** | **Bỏ sót chữ chạy chân trang tin tức** | OCR ngẫu nhiên toàn khung hình. | Phân vùng quét chuyên biệt $y > 0.65$, gắn cờ `is_lower_third`. | [src/ocr_extractor.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/ocr_extractor.py) |
| **6** | **Nhiễu âm thanh làm sai chính tả ASR** | Nhạc nền, tiếng ồn talkshow. | `faster-whisper large-v3` + `vad_filter=True` + prompt tiếng Việt. | [src/asr_transcriber.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/asr_transcriber.py) |
| **7** | **Tràn đĩa 20GB trên Kaggle** | Giải nén hàng vạn file ảnh tĩnh ra đĩa. | Đóng gói `.blob` và nạp vào RAM qua `VirtualBlobReader`. | [src/kaggle_runner.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/kaggle_runner.py) |
| **8** | **Đếm lặp vật thể tĩnh trong video** | Phân tích từng frame độc lập. | `yolov8n.pt` + `ByteTrack` thống kê số lượng track duy nhất trong cú máy. | [src/object_detector.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/object_detector.py) |

### 5.1. Cơ Chế Quét Nối Tiếp Chống Mất Frame (`cap.grab`)
Khi chạy phân tích trên video thời lượng dài hoặc tiếp tục từ checkpoint cũ, việc sử dụng hàm seek `cap.set` của OpenCV thường gây lỗi trượt frame do đặc tính của codec H.264. Pipeline sử dụng kỹ thuật Fast-Forward bằng vòng lặp `cap.grab()`, đạt tốc độ > 1000 fps (do không cần giải mã pixel) để định vị chính xác tuyệt đối tới đúng frame cần xử lý.

---

## 6. Hướng Dẫn Thực Thi Nhanh (Quickstart & Execution Manual)

### 6.1. Chạy 1-Click Trên Kaggle (Khuyến Nghị)

1. **Chuẩn bị Notebook:** Mở [notebooks/kaggle_master_pipeline.ipynb](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/notebooks/kaggle_master_pipeline.ipynb) trên Kaggle.
2. **Cấu hình phần cứng:**
   - **Accelerator:** GPU T4 x2 (hoặc TPU VM v3-8).
   - **Internet:** Bật **ON**.
3. **Thêm dữ liệu:** Bấm **Add Input** chọn Dataset chứa video MP4 hoặc file `.zip`.
4. **Chạy toàn bộ:** Bấm **Run All**. Pipeline sẽ tự động cài đặt thư viện qua `uv`, khởi tạo các mô hình AI, bóc tách thuộc tính và tạo file `release_artifacts.zip` trong `/kaggle/working/` để tải về.

### 6.2. Chạy Cục Bộ Qua Unified Master CLI Runner (`benchmark_runner.py`)

Thư mục [scripts/](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts) cung cấp kịch bản điều phối trung tâm:

```bash
# 1. Chạy 4 bài kiểm thử dữ liệu thật (Keyframes, Vectors, Objects, SQLite FTS5)
python system1-kaggle-pipeline/scripts/benchmark_runner.py --mode steps

# 2. Quét và phân tách cú máy trực tiếp trên video MP4 thô (ví dụ: L21_V001)
python system1-kaggle-pipeline/scripts/benchmark_runner.py --mode raw_video --video L21_V001 --frames 1500

# 3. Quét toàn bộ video không giới hạn frame
python system1-kaggle-pipeline/scripts/benchmark_runner.py --mode raw_video --video L21_V001 --frames 0

# 4. Chạy đối soát song song 10 video mẫu với dữ liệu BTC
python system1-kaggle-pipeline/scripts/benchmark_runner.py --mode 10_videos
```

### 6.3. Đối Soát Trực Quan Side-by-Side Trên Giao Diện Studio

Khởi chạy ứng dụng giao diện đối soát để so sánh trực quan chất lượng keyframe giữa Ban tổ chức và System 1:

```bash
python interactive-test-app/app.py
```
Mở trình duyệt tại địa chỉ `http://localhost:7860` để xem bảng chia đôi màn hình (Nửa trái: Dữ liệu BTC vs Nửa phải: System 1), dòng thời gian trung tâm, nút mở YouTube đúng giây và trình phân tích metadata chi tiết.

---

## 7. Bản Đồ Thư Mục Mã Nguồn (Repository Layout)

```text
system1-kaggle-pipeline/
├── README.md                                    # Cẩm nang kỹ thuật và hướng dẫn triển khai (File này)
├── KEYFRAME_PIPELINE_README.md                  # Sổ tay tổng kết nhánh xử lý Keyframe & Phân loại ranh giới dữ liệu
├── PIPELINE_FLOW_AND_VERIFICATION.md            # Cẩm nang Luồng Triển Khai & Kiểm Tra Tổng Quan Đầu-Cuối
├── EXECUTION_MILESTONES.md                      # Nhật ký thực nghiệm chi tiết & Dữ liệu đo kiểm
├── requirements_kaggle.txt                      # Danh sách thư viện cài đặt nhanh cho môi trường Kaggle
├── configs/
│   └── pipeline_config.yaml                     # File cấu hình tham số mô hình, ngưỡng lọc chất lượng
├── src/
│   ├── frame_timeline.py                        # Phase 00: Packet Counting chống lệch frame tuyệt đối
│   ├── shot_detector.py                         # Phase 01: Cắt cú máy TransNet V2 / Histogram Correlation
│   ├── adaptive_keyframe.py                     # Phase 01: Lấy mẫu keyframe đa dải + Lọc độ nét Laplacian
│   ├── asr_transcriber.py                       # Phase 01: faster-whisper Large-V3 bóc tách lời thoại tiếng Việt
│   ├── ocr_extractor.py                         # Phase 02: EasyOCR bóc tách chữ tiếng Việt & vùng chân trang
│   ├── object_detector.py                       # Phase 02: YOLOv8 + ByteTrack theo dõi và đếm vật thể động
│   ├── vector_extractor.py                      # Phase 02: SigLIP Base trích xuất vector nhúng chuẩn hóa L2
│   ├── semantic_enricher.py                     # Phase 02: Phân tích 6 trường thuộc tính KIS chuyên sâu
│   ├── db_builder.py                            # Phase 03: Đóng gói SQLite FTS5 Unicode và FAISS Index SQ8
│   └── kaggle_runner.py                         # Trình điều phối tự động toàn diện 5 bước trên Kaggle
├── scripts/
│   ├── README.md                                # Hướng dẫn chi tiết các kịch bản kiểm thử
│   ├── benchmark_runner.py                      # Master CLI Runner đa năng (steps, raw_video, 10_videos)
│   ├── validate_subagent_pipeline.py            # Khung kiểm định tự động 5 tiêu chuẩn cho Sub-Agents
│   ├── colab_upload_dataset.py                  # Kịch bản đẩy dữ liệu nhanh từ Colab lên Kaggle
│   └── steps/                                   # Các module kiểm thử 4 bước riêng biệt
└── notebooks/
    ├── colab_drive_to_kaggle_uploader.ipynb     # Notebook cầu nối Drive -> Kaggle Dataset
    └── kaggle_master_pipeline.ipynb             # Notebook thực thi 1-Click trọn gói trên Kaggle
```

---

## 8. Tài Liệu Bàn Giao & Khung Quản Trị Sub-Agents (Rule 11 Compliance)

- **Sổ Tay Nhánh Xử Lý Keyframe:** [KEYFRAME_PIPELINE_README.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/KEYFRAME_PIPELINE_README.md)
- **Cẩm Nang Luồng Vận Hành & Kiểm Định:** [PIPELINE_FLOW_AND_VERIFICATION.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/PIPELINE_FLOW_AND_VERIFICATION.md)
- **Nhật Ký Thực Nghiệm:** [EXECUTION_MILESTONES.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/EXECUTION_MILESTONES.md)
- **Ma Trận Phân Giao Tác Vụ 3 Vai Trò:** [.agents/communication/system1_subagent_task_delegation.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/.agents/communication/system1_subagent_task_delegation.md)
- **Master Handover Prompt Chuyển Ngữ Cảnh:** [.agents/communication/subagent_master_handover_prompt.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/.agents/communication/subagent_master_handover_prompt.md)
- **Script Kiểm Định Tự Động Đầu Ra:** [scripts/validate_subagent_pipeline.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/validate_subagent_pipeline.py)



