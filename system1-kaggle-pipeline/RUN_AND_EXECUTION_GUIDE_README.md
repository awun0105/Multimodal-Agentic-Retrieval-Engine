# CẨM NANG HƯỚNG DẪN KHỞI CHẠY & THỨ TỰ CÁC BƯỚC XỬ LÝ (RUN & EXECUTION GUIDE)

Tài liệu này hướng dẫn chi tiết cách cài đặt, khởi chạy giao diện kiểm duyệt trực quan và giải thích rõ ràng thứ tự tuần tự các bước xử lý dữ liệu trong hệ thống **Multimodal Agentic Retrieval Engine (AIC 2026)**.

---

## 1. Hướng Dẫn Khởi Chạy Nhanh (Quickstart Guide)

### 1.1. Khởi Chạy Web App Trực Quan (1-Click Launcher trên Windows)
Để mở Studio kiểm duyệt trực quan Side-by-Side:
1. Nhấp đúp chuột vào tệp:
   ```bash
   start_interactive_test_app.bat
   ```
2. Trình khởi chạy sẽ tự động kiểm tra thư viện, giải phóng cổng mạng `7860` nếu đang bị chiếm dụng và mở giao diện Web tại địa chỉ:
   ```text
   http://127.0.0.1:7860
   ```

*Hoặc chạy trực tiếp bằng dòng lệnh Python:*
```powershell
python interactive-test-app/launcher.py
```

---

### 1.2. Khởi Chạy Toàn Bộ Pipeline Trên Kaggle (GPU / TPU)
Nếu chạy tiền xử lý hàng loạt trên máy chủ Kaggle:
1. Mở notebook:
   [system1-kaggle-pipeline/notebooks/kaggle_master_pipeline.ipynb](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/notebooks/kaggle_master_pipeline.ipynb)
2. Chọn môi trường phần cứng: **GPU P100 / T4 x 2** hoặc **TPU VM v3-8**.
3. Chạy lệnh: `Run All`. Toàn bộ dữ liệu kết quả sẽ được đóng gói tự động vào `/kaggle/working/unified_output/`.

---

## 2. Thứ Tự Tuần Tự Các Bước Xử Lý (Sequential Step-by-Step Flow)

Quy trình tiền xử lý được chia thành **6 bước tuần tự nghiêm ngặt**, đảm bảo tính độc lập và khả năng kiểm thử độc lập ở từng khâu:

```text
[Video Thô .MP4] 
   │
   ├─► BƯỚC 1: Phân đoạn Cú Máy & Lấy Mẫu Keyframe Thích Ứng (Shot Sampling)
   │
   ├─► BƯỚC 2: Nhận Diện Đa Vật Thể (YOLO) & Bóc Tách OCR Chân Trang
   │
   ├─► BƯỚC 3: Phân Tích Màu Sắc, Bối Cảnh & Ngữ Cảnh Toàn Cú Máy
   │
   ├─► BƯỚC 4: Khử Trùng Lặp Cửa Sổ Trượt & Cứu Ảnh Mờ (Sharpening Fallback)
   │
   ├─► BƯỚC 5: Hợp Nhất Trục Thời Gian Với BTC & Kích Hoạt Frame Cắt Nghĩa
   │
   └─► BƯỚC 6: Đóng Gói Chỉ Mục Tìm Kiếm (FAISS + SQLite FTS5 + Unified Export)
```

---

### Bước 1: Phân Đoạn Cú Máy & Lấy Mẫu Keyframe Thích Ứng
- **Mục tiêu:** Bóc tách ranh giới cú máy (Shot Cut) và chọn ra khung hình đại diện sắc nét nhất.
- **Thuật toán & Cơ chế:**
  * Thu nhỏ khung hình về $320 \times 180$, tính toán biểu đồ màu HSV 2D ($30 \times 32$ bins).
  * Đo tương quan histogram `cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)`:
    - Nếu tương quan $< 0.60$ và độ dài cú máy $\ge 0.4\text{s}$ (12 frames): Đánh dấu Cắt Cú Máy (Hard Cut / Transition).
    - Giới hạn tối đa một cú máy không vượt quá $3.0\text{s}$ (Adaptive Sampling).
  * Tính điểm sắc nét Laplacian Variance trên từng frame. Khung hình có $\text{Sharpness} \ge 35.0$ và mật độ thông tin cao nhất sẽ được chọn làm **Best Candidate**.
  * **Cứu Ảnh Mờ (Sharpening Fallback):** Nếu cả cú máy không có frame nào $\ge 35.0$, hệ thống tự động giữ lại frame rõ nhất trong cú máy đó và tăng cường độ nét qua bộ lọc Unsharp Masking (`is_sharpened_fallback = True`).
- **Đầu ra:** Các file ảnh JPEG chất lượng cao trong `extracted_keyframes/{video_id}/` và ảnh WebP thu nhỏ trong `extracted_thumbnails/{video_id}/`.

---

### Bước 2: Nhận Diện Đa Vật Thể Chi Tiết & Bóc Tách Chữ OCR Chân Trang
- **Mục tiêu:** Bắt trọn thông tin vật thể (cả nhỏ và lớn) cùng nội dung văn bản hiển thị trên màn hình.
- **Thuật toán & Cơ chế:**
  * **Nhận diện vật thể (Object Detection):** Nạp mô hình YOLOv8 với ngưỡng `conf = 0.15` và kích thước suy luận chuẩn `imgsz = 640`. Dịch toàn bộ nhãn COCO sang tiếng Việt chuẩn tắc (`dog` -> Chó, `bread` -> Bánh mì, `flag` -> Cờ, `cup` -> Cốc/Ly, `chair` -> Ghế...).
  * **Đếm số lượng vật thể (Object Counting):** Tổng hợp và sắp xếp tần suất xuất hiện: `Cờ x 2, Người x 1, Bánh mì x 1`.
  * **OCR chân trang (Lower-Third OCR):** Sử dụng EasyOCR tiếng Việt, lọc các hộp thoại có tọa độ $y > 0.65$ (vùng bản tin, phụ đề, bảng tên nhân vật) và khử trùng lặp chuỗi qua chỉ số tương đồng Jaccard $\ge 0.85$.

---

### Bước 3: Phân Tích Màu Sắc, Bối Cảnh & Ngữ Cảnh Toàn Cú Máy
- **Mục tiêu:** Gán nhãn môi trường và hiểu ngữ cảnh tổng thể của toàn bộ cú máy (Shot-level context).
- **Thuật toán & Cơ chế:**
  * **Năng lượng nét chữ & Màu chủ đạo:** Dùng toán tử Sobel phát hiện mật độ nét tương phản cao (`text_density_pct`) và phân loại màu sắc chủ đạo qua không gian màu HSV (Đỏ Thời Sự, Xanh Dương, Vàng/Cam, Trắng/Sáng, Đen/Tối, Đa Sắc).
  * **Nhận diện bối cảnh (Scene Environment):** Tự động phát hiện loại môi trường (Trường quay Thời sự / Studio, Đường phố / Giao thông, Thể thao / Sân vận động, Nước / Biển, Cây cối / Thiên nhiên, Trong nhà / Văn phòng).
  * **Suy đoán ý nghĩa toàn cú máy (`shot_contextual_meaning`):** Bóc tách hoạt động chính và từ khóa văn bản nổi bật:
    - `Dẫn bản tin trường quay thời sự | Từ khóa: [Thời sự, 19h]`
    - `Di chuyển giao thông đường phố | Từ khóa: [Biển báo, Ngã tư]`
    - `Thi đấu thể thao / Tranh chấp bóng | Từ khóa: [Trực tiếp, V-League]`
  * **Bóc tách ASR Lời Thoại:** Chạy `faster-whisper large-v3` bóc tách lời thoại tiếng Việt có dấu kèm timestamp phục vụ truy vấn Video QA.

---

### Bước 4: Khử Trùng Lặp Cửa Sổ Trượt & Phân Loại Trực Quan
- **Mục tiêu:** Loại bỏ sự trùng lặp thị giác giữa các keyframe liền kề mà không làm mất thông tin thời gian.
- **Thuật toán & Cơ chế:**
  * Áp dụng cửa sổ trượt 3 frame liên tiếp, đo độ tương đồng thị giác đa phương thức ($S_{\text{visual}}$).
  * **Quy tắc ngoại lệ OCR & Vật thể:** Nếu văn bản OCR hoặc danh sách vật thể có sự biến thiên rõ rệt $\rightarrow$ Giữ nguyên là keyframe độc lập, không gộp.
  * **Phân loại lý do đề xuất lọc bỏ:**
    - Khung hình có độ nét kém hơn Anchor rõ rệt ($< 0.75 \times \text{Anchor}$): Đánh dấu **Viền Đỏ Đậm (`#ff5555`)** kèm tag `[Đề Xuất Lọc Bỏ - Độ nét kém hơn Anchor #...]`.
    - Khung hình mờ dưới ngưỡng: `[Đề Xuất Lọc Bỏ - Độ nét thấp < 30.0 (Ảnh mờ)]`.

---

### Bước 5: Hợp Nhất Trục Thời Gian Chung Với Ban Tổ Chức (BTC)
- **Mục tiêu:** Đồng bộ 100% keyframe của BTC và System 1 trên cùng một dòng thời gian chung.
- **Thuật toán & Cơ chế:**
  * Chuẩn hóa `pts_time_sec` cho cả BTC và System 1, sắp xếp xen kẽ tăng dần theo thời gian thực.
  * **Gộp mốc trùng tuyệt đối ($|\Delta t| \le 0.05\text{s}$):** Tích hợp dữ liệu thành 1 bản ghi duy nhất, kế thừa mã nộp bài BTC và metadata chi tiết của System 1.
  * **Kích hoạt Frame Cắt Nghĩa (Virtual Reference Proxy):** Đối với các frame lân cận có độ tương đồng thị giác cao ($\ge 0.88$):
    - Khung hình của BTC hoặc frame có Info Score cao nhất được chọn làm **Anchor Frame**.
    - Khung hình tương đồng còn lại được chuyển thành **Frame Cắt Nghĩa** với **Viền Tím Neon (`#bd93f9`)**, hiển thị badge `[Frame Cắt Nghĩa +Δt]` (Zero Disk Waste - không nhân bản file ảnh).
  * **Thẻ `[BTC-xử lý]`:** Tự động phát hiện frame BTC đơn sắc hoặc có mật độ thông tin thấp để hiển thị viền đỏ/cam và gắn badge `[BTC-xử lý: Mật độ thông tin thấp]`.

---

### Bước 6: Đóng Gói Chỉ Mục Tìm Kiếm & Xuất Bộ Dữ Liệu Hợp Nhất
- **Mục tiêu:** Tạo lập cơ sở dữ liệu tìm kiếm cục bộ siêu nhanh phục vụ thi trực tiếp.
- **Đầu ra hoàn chỉnh:**
  1. **SQLite Database (`metadata.db`):** Chứa bảng `keyframes`, bảng `text_fts` (FTS5 Unicode61 tìm kiếm OCR/Metadata) và bảng `asr_fts` (tìm kiếm lời thoại ASR Video QA).
  2. **FAISS Index (`siglip.faiss`):** Chỉ mục vector nhúng SigLIP 768D (Cosine Inner Product) cho truy vấn hình ảnh và văn bản KIS.
  3. **Bộ Dữ Liệu Hợp Nhất (`unified_keyframes.json` & `unified_keyframes.csv`):** Chứa toàn bộ 8 trường metadata chuẩn tắc của tất cả keyframe đã hợp nhất.

---

## 3. Hướng Dẫn Chạy Kiểm Thử Độc Lập Các Bước (Unit Tests)

Để kiểm chứng tính đúng đắn của từng bước, chạy các lệnh sau trong PowerShell:

```powershell
# Kiểm thử Bước 1: Bắt Keyframe Enter/Exit và Crowd Suppression
python system1-kaggle-pipeline/scripts/steps/test_step1_event_keyframes.py

# Kiểm thử Bước 2: Khử trùng lặp OCR và phân vùng chân trang
python system1-kaggle-pipeline/scripts/steps/test_step2_video_ocr_dedup.py

# Kiểm thử Bước 3: Tra cứu Video QA qua ASR timestamped FTS5
python system1-kaggle-pipeline/scripts/steps/test_step3_asr_timestamp_qa.py

# Kiểm thử Bước 4: Phân loại thể loại video và sinh trọng số RRF
python system1-kaggle-pipeline/scripts/steps/test_step4_genre_classifier.py

# Kiểm thử Bước 5: Đồng bộ Timeline BTC, Frame Cắt Nghĩa viền tím, Đa Tag & Chống crash NaN
python system1-kaggle-pipeline/scripts/steps/test_step5_timeline_merge_dedup.py
```

*Tất cả 5 bài kiểm thử đều được thiết kế độc lập, chạy trực tiếp trên dữ liệu mẫu thực tế và đạt tỷ lệ vượt qua **100% ALL PASS**.*
