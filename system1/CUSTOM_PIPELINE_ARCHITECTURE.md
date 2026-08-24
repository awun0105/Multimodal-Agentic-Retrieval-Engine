# Kiến Trúc Kênh Xử Lý Tự Chủ System 1 (System 1 Custom Ingestion Pipeline Blueprint)

Tài liệu này cung cấp thiết kế kiến trúc, lý do kỹ thuật và hướng dẫn triển khai cho **Kênh Xử Lý Dữ Liệu Tự Chủ (Custom Offline Data Factory)** của System 1. Kênh này được xây dựng nhằm giải quyết triệt để các lỗi sai lệch dữ liệu từ Ban tổ chức (BTC), tối ưu hóa chất lượng trích xuất Keyframe, và nâng cao độ chính xác truy xuất đa phương thức cho cuộc thi AIC 2026.

---

## 1. Lý Do Cần Kênh Xử Lý Riêng (Why a Custom Pipeline is Essential)

Dữ liệu mặc định do BTC cung cấp (Keyframes, CLIP features, Objects) tồn tại 4 hạn chế kỹ thuật chí mạng:

1. **Hiện tượng Lệch Khung Hình (Frame ID Drift):**
   - BTC decode video bằng ước lượng timestamp truyền thống (`pts_time * fps`), dẫn đến việc số thứ tự khung hình trong bảng `map-keyframes` bị lệch từ 1 đến 5 frame so với khung hình thực tế trong video gốc khi chấm điểm tự động.
2. **Trích Xuất Keyframe Kém Hiệu Quả (Suboptimal Keyframe Sampling):**
   - BTC sử dụng giải thuật lấy mẫu cố định theo chu kỳ thời gian (Uniform Interval) hoặc ngưỡng màu đơn giản. Điều này làm trôi mất các khoảnh khắc hành động then chốt (Action Climax), hoặc tạo ra nhiều khung hình bị nhòe chuyển động (Motion Blur), khung hình chuyển cảnh đen.
3. **Mô Hình Vector Cũ & Độ Phân Giải Thấp:**
   - Tập `clip-features-32` của BTC được trích xuất bằng mô hình OpenAI CLIP ViT-B/32 (từ năm 2021), độ phân giải đầu vào chỉ 224x224, khả năng nhận biết ngữ cảnh tiếng Việt và chi tiết thể thao bị hạn chế đáng kể so với các mô hình Vision-Language hiện đại.
4. **Thiếu Hụt Thông Tin Đa Phương Thức (Multimodal Blindspots):**
   - Dữ liệu BTC không có bóc tách giọng nói (ASR), không có cấu trúc phân đoạn cảnh logic (Scene Grouping) và thông tin OCR bị rời rạc, làm giảm tỷ lệ thành công của bài toán Video Q&A và TRAKE.

---

## 2. Kiến Trúc 4 Tầng Tự Chủ Của System 1 (4-Stage Modular Pipeline)

Kênh xử lý riêng của System 1 được thiết kế theo mô hình mô-đun hóa độc lập (Decoupled Modular Architecture):

```text
[Video Gốc MP4 + Metadata Thô]
               │
               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ TẦNG 1: CHUẨN HÓA KHUNG HÌNH & BÓC TÁCH ÂM THANH (PHASE 00)             │
│ - FFmpeg Packet Counting: Giải mã đếm gói tuyệt đối, chống lệch frame   │
│ - Tạo frame_timeline/{video_id}.parquet & trích xuất audio 16kHz mono   │
│ - Phân chia Batch tự động (assign-batches)                              │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ TẦNG 2: PHÁT HIỆN CÚ MÁY & TRÍCH XUẤT KEYFRAME THÔNG MINH (PHASE 01)     │
│ - TransNet V2 Shot Boundary Detection: Cắt video theo cú máy thực tế    │
│ - Smart Keyframe Selector: Lấy mẫu tại các dải 20% - 50% - 80% của shot │
│ - Lọc ảnh mờ chuyển động (Laplacian Motion/Sharpness Filter)             │
│ - Faster-Whisper Large-V3: Bóc tách lời thoại tiếng Việt chính xác     │
│ - Gemini Structured API: Sinh Shot Caption song ngữ & Gom Scene logic   │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ TẦNG 3: TRÍCH XUẤT VECTOR ĐA PHƯƠNG THỨC & OCR NÂNG CAO (PHASE 02)      │
│ - SigLIP Base (Patch16-224): Trích xuất vector nhúng chuẩn hóa L2       │
│ - Vintern-1B / EasyOCR: Bóc tách chữ biển số, áo đấu, bảng tỉ số       │
│ - Đóng gói Checkpoint SHA256 từng video để chống mất dữ liệu khi chạy   │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ TẦNG 4: HỢP NHẤT DỮ LIỆU & XÂY DỰNG CHỈ MỤC TÌM KIẾM (PHASE 03)         │
│ - SQLite WAL Database: Tạo bảng FTS5 toàn diện (Title, OCR, ASR, Captions)│
│ - FAISS Index: Xây dựng chỉ mục vector lượng tử hóa CPU-Friendly (SQ8)  │
│ - Xuất bản READY.json hoàn chỉnh cho System 2 sử dụng                   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Chi Tiết Từng Mô-Đun Tối Ưu

### 3.1. Mô-Đun 1: Packet Counting & Đồng Bộ Khung Hình Tuyệt Đối
- **Cơ chế:** Sử dụng FFmpeg ở chế độ đếm gói tin (`av_read_frame` packet iteration) để gán cho mỗi khung hình một chỉ số `frame_id` duy nhất và mốc thời gian `pts_time` chính xác.
- **Đầu ra:** Bảng `frame_timeline/{video_id}.parquet` đóng vai trò là "nguồn sự thật duy nhất" (Source of Truth) cho toàn bộ hệ thống, loại bỏ hoàn toàn lỗi lệch số thứ tự khung hình khi nộp bài.

### 3.2. Mô-Đun 2: Trích Xuất Keyframe Thông Minh (Smart Keyframe Extraction)
- **Cắt cú máy bằng TransNet V2:** Thay vì lấy mẫu đều đặn theo giây, mô hình TransNet V2 nhận diện chính xác điểm chuyển cảnh (Hard Cuts và Dissolves/Fades).
- **Lấy mẫu đa dải (Multi-Band Selection):**
  - Trong mỗi shot, hệ thống trích xuất 3 khung hình ứng viên tại các vị trí $20\%$, $50\%$, và $80\%$ độ dài shot.
  - Áp dụng thuật toán tính phương sai Laplacian ($\text{Var}(\nabla^2 I)$) để tự động loại bỏ các khung hình bị nhòe chuyển động hoặc chớp tối.
- **Tạo ảnh thu nhỏ (Thumbnails) tối ưu:** Mỗi keyframe được lưu ở cả định dạng Full-HD (cho chế độ Rich Mode) và định dạng WebP thu nhỏ 128x128 px (cho chế độ Lean Mode).

### 3.3. Mô-Đun 3: Trích Xuất Vector SOTA (SigLIP Base & Modern VLM)
- **Mô hình Trọng tâm:** `google/siglip-base-patch16-224` (SigLIP Base).
- **Ưu điểm vượt trội so với CLIP ViT-B/32 cũ của BTC:**
  - Sử dụng hàm mất mát Sigmoid Loss (thay vì Softmax thông thường), tối ưu hóa khả năng phân tách không gian ngữ nghĩa giữa ảnh và câu truy vấn.
  - Hiểu tốt hơn về ngữ cảnh hành động thể thao, màu sắc trang phục, mối quan hệ không gian.
  - Vector sinh ra có độ dài 768 chiều (hoặc 512 chiều) và được chuẩn hóa Euclidean $L_2\text{-Norm} = 1.0$ để thực hiện tìm kiếm Cosine Similarity bằng tích vô hướng Inner Product trong FAISS.

### 3.4. Mô-Đun 4: Nhận Diện Giọng Nói (ASR) & Chữ (OCR) Chuyên Sâu
- **ASR:** Chạy `faster-whisper large-v3` trên GPU (CTranslate2 INT8/FP16), trích xuất toàn bộ lời bình luận viên, hội thoại nhân vật kèm mốc thời gian mili-giây và liên kết trực tiếp với từng shot (`shot_transcript_links.parquet`).
- **OCR:** Chạy mô hình chuyên biệt cho tiếng Việt `Vintern-1B` kết hợp `EasyOCR` để ghi nhận toàn bộ chữ trên màn hình (bảng tỉ số thể thao, biển hiệu, tên cầu thủ).

---

## 4. Quy Trình Vận Hành & Khả Năng Mở Rộng (Execution & Scaling)

### 4.1. Chạy Tiền Xử Lý Phân Tán Trên Cloud (Kaggle / Colab)
Nhờ kiến trúc Batch của System 1, toàn bộ quá trình xử lý video nặng có thể được phân tán:
1. `notebooks/00_master_ingestion_and_assignment.ipynb`: Quét danh sách video thô, tạo bảng timeline và chia thành $N$ batch nhỏ (20-50 video/batch).
2. `notebooks/01_worker_structure_pipeline.ipynb`: Chạy song song nhiều worker (mỗi worker nhận 1 batch) để trích xuất shots, keyframes, ASR, captions.
3. `notebooks/02_worker_feature_enrichment.ipynb`: Chạy trích xuất vector SigLIP và OCR.
4. `notebooks/03_merge_validate_index_release.ipynb`: Gom các tệp artifact từ các worker, xây dựng cơ sở dữ liệu `runtime.sqlite` và chỉ mục `keyframes.faiss`.

### 4.2. Khả Năng Tương Thích Ngược (Dual-Pipeline Compatibility)
Hệ thống duy trì khả năng hoạt động song song:
- **Baseline Path:** Có thể nạp ngay dữ liệu có sẵn của BTC (`clip-features-32` + `map-keyframes`) để kiểm thử giao diện và chạy demo ngay tức thì.
- **Custom Production Path:** Nạp dữ liệu chất lượng cao do System 1 tự xử lý để thi đấu chính thức với độ chính xác và độ ổn định cao nhất.
