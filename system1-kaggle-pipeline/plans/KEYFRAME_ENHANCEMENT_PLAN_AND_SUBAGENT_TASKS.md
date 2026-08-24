<!-- 
================================================================================
AGENT CONTEXT & PROTOCOL HEADER (DÀNH CHO CÁC AI AGENT KẾ NHIỆM)
- Tên tài liệu: system1-kaggle-pipeline/plans/KEYFRAME_ENHANCEMENT_PLAN_AND_SUBAGENT_TASKS.md (TẦNG 4: Sub-Agent Plan & Live Discussion Ledger)
- Vai trò trong hệ thống: Kế hoạch phân rã 4 phân hệ nâng cấp, Ma trận phân công 3 vai trò (Orchestration, Execution, Validation) và Sổ cái Nhật ký Thảo luận Kỹ thuật phát sinh.
- Ràng buộc quy tắc (Rules Compliance):
  * Rule 1: Giải thích rõ ràng mục tiêu ở đầu mỗi mục lớn.
  * Rule 10: Nguyên tắc Append-Only đối với Nhật ký thảo luận phát sinh (Mục 4).
  * Rule 11: Mô hình Quản trị 3 vai trò và Hợp đồng dữ liệu JSON/Dict.
  * Rule 12: Đồng bộ hóa với CONVERSATION_README.md.
  * Rule 13: Chủ động đặt câu hỏi làm rõ và thảo luận đề xuất cải tiến tính năng.
  * Rule 14: Quản trị kế hoạch trong plans/ và ghi nhận nhật ký thảo luận phát sinh trực tiếp vào file này.
  * Tone Constraint: Tuyệt đối KHÔNG dùng emoji/icon ở bất kỳ đâu.
- Tệp liên kết thượng nguồn (Upstream): KEYFRAME_PIPELINE_README.md, .agents/rules/user_rules.md
- Tệp liên kết hạ nguồn (Downstream): src/ (source code), scripts/steps/ (test cases)
- Kịch bản kiểm thử tương ứng: python system1-kaggle-pipeline/scripts/steps/test_step1_event_keyframes.py
================================================================================
-->

# Kế Hoạch Nâng Cấp Hệ Thống Keyframe & Ma Trận Phân Việc Cho Sub-Agents (Keyframe Enhancement Plan & Sub-Agent Task Matrix)

Tài liệu này xác định kế hoạch kỹ thuật phân rã 4 phân hệ nâng cấp cho nhánh `feature/system1-keyframe-pipeline`, phân công nhiệm vụ theo **Mô hình Quản trị 3 Vai trò (Three-Role Agent Framework)** theo Quy Tắc 11, cung cấp kịch bản kiểm thử độc lập trên dữ liệu thật, và duy trì **Nhật Ký Tình Trạng, Vấn Đề & Thảo Luận Kỹ Thuật Phát Sinh** cho toàn bộ các Agent tiếp theo.

---

## 1. Tổng Quan 4 Bước Nâng Cấp Hệ Thống (Enhancement Steps Overview)

```text
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                     HỆ THỐNG 4 BƯỚC NÂNG CẤP SYSTEM 1 (VIETNAMESE & KIS FOCUS)                  │
├─────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                 │
│  [BƯỚC 1: TRÍCH XUẤT KEYFRAME THEO SỰ KIỆN VẬT THỂ]                                            │
│  - Theo dõi ByteTrack (first_seen, last_seen)                                                   │
│  - Heuristic ức chế đám đông: <= 5 người (Event Keyframes) vs > 5 người (Uniform 20-50-80%)     │
│  - Bộ lọc thời lượng ổn định >= 0.8s chống nhiễu chớp tắt                                       │
│                                                                                                 │
│  [BƯỚC 2: TRÍCH XUẤT OCR TRỰC TIẾP & KHỬ TRÙNG LẶP CẤP CÚ MÁY]                                 │
│  - Phân vùng không gian: Chân trang y > 0.65 (News Tickers) vs Trung tâm (Biển báo, conf >= 0.7)│
│  - Khử trùng lặp cấp cú máy (Shot-Level Deduplication qua Jaccard >= 0.85)                     │
│  - Dung lượng DB FTS5 siêu nhẹ (< 50MB)                                                         │
│                                                                                                 │
│  [BƯỚC 3: CƠ SỞ DỮ LIỆU ASR PHÂN ĐOẠN THEO TIMESTAMP CHO VIDEO QA]                             │
│  - Bóc tách lời thoại tiếng Việt có dấu qua faster-whisper large-v3 FP16                        │
│  - Bảng SQLite asr_segments + bảng ảo asr_fts (unicode61 remove_diacritics 2)                   │
│  - Tốc độ tra cứu Video QA < 2ms, hỗ trợ nhảy chính xác mốc thời gian                           │
│                                                                                                 │
│  [BƯỚC 4: PHÂN LOẠI THỂ LOẠI VIDEO TỪ METADATA (GENRE CLASSIFIER)]                              │
│  - Nhận diện 5 nhóm: news, education, sports, entertainment, general                            │
│  - Tự động điều chỉnh trọng số tìm kiếm RRF (Dynamic Weight Routing) giữa Visual và Text/ASR    │
│                                                                                                 │
│  [BƯỚC 5: HỢP NHẤT TIMELINE BTC-SELF, ĐẾM VẬT THỂ & KHỬ TRÙNG LẶP ẢO CẮT NGHĨA]                 │
│  - Hợp nhất trục thời gian chính xác, gộp frame trùng mốc (|Δt| <= 0.05s)                       │
│  - Đếm số lượng vật thể chuẩn hóa 'Nhãn x Số lượng' (Cờ x 5, Người x 2)                         │
│  - Cửa sổ trượt 3 keyframe đo tương đồng thị giác (>= 0.92) kèm Ngoại lệ OCR (giữ text mới)     │
│  - Tạo Frame Cắt Nghĩa (Virtual Link) không tốn đĩa, gắn tag delta_time và hiển thị viền tím    │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Ma Trận Phân Công Tác Vụ Sub-Agents (Rule 11 Compliance)

### Step 1: Trích Xuất Keyframe Theo Sự Kiện Vật Thể (Object Event Tracking)
- **Module mã nguồn:** `src/object_detector.py` và `src/adaptive_keyframe.py`.
- **Nhiệm vụ 3 vai trò:**
  - **Orchestration Agent:** Kết nối luồng giải mã video OpenCV, nạp model YOLOv8n, điều phối gọi ByteTrack ở 5 FPS (`vid_stride=5`), gom nhóm tracklets theo shot boundary.
  - **Execution Agent:** Cài đặt hàm `extract_object_event_keyframes()`:
    - Tính toán số lượng người duy nhất trong shot `len(unique_persons)`.
    - Nếu $\le 5$: Lấy keyframe tại `first_seen_frame` và `last_seen_frame` của các vật thể có `duration >= 0.8s`.
    - Nếu $> 5$: Lấy keyframe đều 20%, 50%, 80%.
    - Lọc Laplacian $\ge 40.0$ và nén WebP 128x128.
  - **Validation Agent:** Chạy kịch bản kiểm thử độc lập `scripts/steps/test_step1_event_keyframes.py` trên video thực tế `L21_V001.mp4`.
- **Ràng buộc hiệu năng:** Tốc độ tracking $\ge 60\text{ fps}$ trên GPU, không làm tăng quá 25% tổng số lượng keyframe.

---

### Step 2: Trích Xuất OCR Trực Tiếp & Khử Trùng Lặp Cấp Cú Máy
- **Module mã nguồn:** `src/ocr_extractor.py`.
- **Nhiệm vụ 3 vai trò:**
  - **Orchestration Agent:** Nhận luồng keyframe của từng shot, trích xuất ảnh OpenCV BGR, chuyển đổi sang EasyOCR tiếng Việt.
  - **Execution Agent:** Cài đặt hàm `extract_shot_deduped_ocr()`:
    - Cắt vùng chân trang $y > 0.65$ (`is_lower_third = 1`) và vùng trung tâm $0.1 < y \le 0.65$ (`is_lower_third = 0`).
    - Tính độ tương đồng Jaccard giữa các câu văn trong cùng cú máy; nếu $\ge 0.85$ thì chỉ lưu chuỗi dài và rõ nhất.
  - **Validation Agent:** Chạy kịch bản kiểm thử độc lập `scripts/steps/test_step2_video_ocr_dedup.py` trên 10 ảnh mẫu có chữ tin tức chân trang.
- **Ràng buộc hiệu năng:** Tốc độ OCR $\le 30\text{ms}$/frame, dung lượng chuỗi text lưu trữ trong SQLite $\le 50\text{MB}$ cho 1,000 video.

---

### Step 3: Lưu Trữ ASR Phân Đoạn Theo Timestamp Phục Vụ Video QA
- **Module mã nguồn:** `src/asr_transcriber.py` và `src/db_builder.py`.
- **Nhiệm vụ 3 vai trò:**
  - **Orchestration Agent:** Tách luồng audio WAV 16kHz từ MP4 qua `ffmpeg`, nạp vào `faster-whisper large-v3`.
  - **Execution Agent:**
    - Xuất danh sách `[{"start_sec": float, "end_sec": float, "text": str}]`.
    - Tạo bảng `asr_segments` và bảng ảo `asr_fts` trong SQLite (`unicode61 remove_diacritics 2`).
  - **Validation Agent:** Chạy kịch bản kiểm thử độc lập `scripts/steps/test_step3_asr_timestamp_qa.py`, truy vấn 5 câu hỏi Video QA bằng tiếng Việt có/không dấu.
- **Ràng buộc hiệu năng:** Độ trễ tìm kiếm FTS5 $\le 2\text{ms}$, mốc thời gian khớp chính xác với âm thanh gốc.

---

### Step 4: Phân Loại Thể Loại Video Từ Metadata (Genre Classifier)
- **Module mã nguồn:** `src/genre_classifier.py` [NEW].
- **Nhiệm vụ 3 vai trò:**
  - **Orchestration Agent:** Đọc metadata `videos_meta` (tiêu đề, tác giả, mô tả) trước khi chạy pipeline.
  - **Execution Agent:** Cài đặt lớp `VideoGenreClassifier`:
    - Dùng biểu thức chính quy (Regex) và tập từ khóa tiếng Việt để phân loại: `news`, `education`, `sports`, `entertainment`, `general`.
    - Trả về cấu hình trọng số tìm kiếm `search_weight_profile = {"dense_weight": float, "sparse_weight": float}`.
  - **Validation Agent:** Chạy kịch bản kiểm thử độc lập `scripts/steps/test_step4_genre_classifier.py` trên 20 tiêu đề video thực tế.
- **Ràng buộc hiệu năng:** Tốc độ phân loại $\le 0.1\text{ms}$/video, độ chính xác phân loại $\ge 95\%$ trên dữ liệu mẫu.

---

### Step 5: Hợp Nhất Timeline BTC-Self, Đếm Số Lượng Vật Thể & Khử Trùng Lặp Ảo (Frame Cắt Nghĩa)
- **Module mã nguồn:** `src/timeline_synchronizer.py` [NEW].
- **Nhiệm vụ 3 vai trò:**
  - **Orchestration Agent:** Nạp danh sách keyframe BTC (`map-keyframes`) và keyframe System 1 (`benchmark_summary.csv`), đưa lên trục thời gian chung.
  - **Execution Agent:** Cài đặt lớp `TimelineSynchronizer`:
    - `format_object_counts()`: Chuyển đổi nhãn phát hiện sang chuỗi `"Nhãn x Số lượng"` (ví dụ: `"Cờ x 5, Người x 2"`).
    - `merge_and_sort_timeline()`: Gộp các frame trùng mốc $|\Delta t| \le 0.05\text{s}$, gán `btc_frame_idx`.
    - `sliding_window_deduplicate()`: Cửa sổ trượt 3 frame đo độ tương đồng thị giác ($\ge 0.92$). Nếu OCR khác biệt $\rightarrow$ Giữ nguyên keyframe độc lập. Nếu trùng lặp $\rightarrow$ Chọn Anchor Frame (ưu tiên BTC / Info Value Score cao nhất), các frame còn lại thành Frame Cắt Nghĩa (Virtual Frame) với tag delta thời gian và viền tím Violet (`#bd93f9`).
  - **Validation Agent:** Chạy kịch bản kiểm thử độc lập `scripts/steps/test_step5_timeline_merge_dedup.py` trên 5 tình huống thực tế.
- **Ràng buộc hiệu năng:** Tốc độ xử lý timeline $\le 5\text{ms}$/video, Zero Disk Waste (không nhân bản file ảnh vật lý thừa).

---

## 3. Danh Sách Các Kịch Bản Kiểm Thử Độc Lập (Standalone Test Suites)

Các script kiểm thử này được thiết kế để chạy độc lập từ terminal trên dữ liệu thật mà không cần chạy toàn bộ pipeline lớn:

1. **Test Step 1:** `python system1-kaggle-pipeline/scripts/steps/test_step1_event_keyframes.py`
   - *Mục tiêu:* Kiểm tra việc lấy keyframe tại mốc xuất hiện/biến mất của người và kiểm chứng quy tắc $\le 5$ người.
2. **Test Step 2:** `python system1-kaggle-pipeline/scripts/steps/test_step2_video_ocr_dedup.py`
   - *Mục tiêu:* Kiểm tra khả năng bắt tin tức chân trang $y > 0.65$ và khử trùng lặp văn bản trong cùng một shot.
3. **Test Step 3:** `python system1-kaggle-pipeline/scripts/steps/test_step3_asr_timestamp_qa.py`
   - *Mục tiêu:* Kiểm tra việc tạo bảng `asr_fts` và tốc độ tra cứu câu hỏi Video QA có dấu / không dấu.
4. **Test Step 4:** `python system1-kaggle-pipeline/scripts/steps/test_step4_genre_classifier.py`
   - *Mục tiêu:* Kiểm tra 20 trường hợp tiêu đề video mẫu để gán đúng nhãn thể loại và trọng số RRF.
5. **Test Step 5:** `python system1-kaggle-pipeline/scripts/steps/test_step5_timeline_merge_dedup.py`
   - *Mục tiêu:* Kiểm tra gộp mốc thời gian $|\Delta t| \le 0.05\text{s}$, định dạng đếm số lượng vật thể 'Nhãn x Số lượng', cửa sổ trượt 3 frame tạo Frame Cắt Nghĩa viền tím và quy tắc Ngoại lệ OCR.

---

## 4. Nhật Ký Tình Trạng, Vấn Đề & Thảo Luận Kỹ Thuật Phát Sinh (Live Issue, Discussion & Resolution Ledger)

Mục này được cập nhật liên tục bởi các Sub-Agent và Agent kế nhiệm để ghi nhận các điểm thảo luận, vấn đề phát sinh và giải pháp đã chốt:

### Mốc 23/08/2026: Khởi Tạo Kế Hoạch 4 Phân Hệ Nâng Cấp
- **Thảo luận 1 (Về việc lọc nhiễu vật thể xuất hiện chớp nhoáng):**
  - *Vấn đề:* Nếu một người chỉ lướt qua ống kính trong 0.1 giây hoặc do nhận diện sai của YOLO, việc lấy keyframe sẽ làm loãng tập dữ liệu.
  - *Giải pháp đã chốt:* Thêm điều kiện ràng buộc `duration >= 0.8s` (ít nhất 4 frames liên tục ở 5 FPS) mới kích hoạt sự kiện `object_entered`.
- **Thảo luận 2 (Về lo ngại bùng nổ dung lượng OCR):**
  - *Vấn đề:* Sợ quét OCR toàn video sẽ gây tốn bộ nhớ và chậm tìm kiếm.
  - *Giải pháp đã chốt:* Dùng phân vùng không gian chân trang và khử trùng lặp Jaccard $\ge 0.85$ cấp cú máy, đưa dung lượng toàn bộ DB xuống dưới $50\text{MB}$.
- **Thảo luận 3 (Về phân loại thể loại video):**
  - *Vấn đề:* Có cần dùng LLM nặng để phân loại video không?
  - *Giải pháp đã chốt:* Dùng Rule-based Regex và Keyword Matching trên Tiêu đề/Tác giả vì tốc độ siêu nhanh ($<0.1\text{ms}$) và độ chính xác cực cao trên dữ liệu truyền hình/tin tức Việt Nam.

### Mốc 23/08/2026: Bổ Sung Step 5 - Hợp Nhất Timeline BTC-Self & Khử Trùng Lặp Ảo Cắt Nghĩa
- **Thảo luận 4 (Về định dạng đếm số lượng vật thể):**
  - *Yêu cầu từ User:* Đếm số lượng vật thể và hiển thị rõ ràng, ví dụ "Cờ x 5, Người x 2" để dễ truy vấn định lượng trong các câu hỏi KIS.
  - *Giải pháp đã chốt:* Xây dựng hàm `TimelineSynchronizer.format_object_counts()` tự động dịch nhãn COCO sang tiếng Việt chuẩn tắc và đếm tần suất. Lưu vào cột `objects_and_counts` và nạp vào bảng ảo FTS5 để hỗ trợ tìm kiếm toàn văn trực tiếp.
- **Thảo luận 5 (Về xử lý trùng lặp trong cửa sổ trượt 3 frame & Ngoại lệ OCR):**
  - *Yêu cầu từ User:* So sánh 3 keyframe liền kề, nếu trùng lặp cao thì lưu dạng frame cắt nghĩa có tag $+/-$ giây, ưu tiên giữ frame BTC; trừ khi OCR khác biệt thì phải giữ nguyên. Hiển thị viền tím cho frame cắt nghĩa.
  - *Giải pháp đã chốt:*
    1. Thiết lập ngưỡng tương đồng thị giác $S \ge 0.92$ trong cửa sổ trượt 3 frame.
    2. Bổ sung cơ chế Ngoại lệ OCR: Nếu Jaccard giữa 2 chuỗi OCR $< 0.60$ (văn bản mới), lập tức giữ nguyên là Keyframe độc lập.
    3. Với các frame trùng lặp còn lại: Lưu dưới dạng **Virtual Frame (Frame Cắt Nghĩa)** — không tạo thêm file ảnh trên đĩa (Zero Disk Waste), gán `delta_time_sec` (ví dụ `+1.2s`, `-0.8s`), liên kết tới `anchor_frame_idx` và render trên UI với khuôn viền màu tím Neon / Violet (`#bd93f9`).

### Mốc 23/08/2026: Hoàn Thiện Khung Trực Quan Metadata, Cứu Ảnh Mờ & Bộ Dữ Liệu Hợp Nhất Cuối Cùng
- **Thảo luận 6 (Về cơ chế cứu ảnh mờ Sharpening Fallback):**
  - *Vấn đề từ User:* Nếu trong cú máy không có frame nào đủ nét ($\ge 35.0$) mà xóa luôn thì sẽ làm mất hoàn toàn cú máy. Cần ưu tiên ảnh rõ nét, nếu không có thì lấy ảnh mờ nhất làm nét lên (Sharpening Fallback).
  - *Giải pháp đã chốt:* Xây dựng hàm `enhance_frame_sharpness(frame_bgr)` dùng Unsharp Masking (`cv2.GaussianBlur` + `cv2.addWeighted`). Trong `extract_video_keyframes_for_duration`, nếu toàn bộ cú máy không có frame nào $\ge 35.0$, lấy frame fallback tốt nhất, áp dụng làm nét và gán `is_sharpened_fallback = True`, viền vàng cam/xanh lá.
- **Thảo luận 7 (Về không xóa nhầm khi cùng số người & Đánh dấu Viền Đỏ Đậm):**
  - *Vấn đề từ User:* Một số ảnh dù khác ngữ cảnh nhưng vẫn bị lọc nhầm do cùng số người; đồng thời cần hiển thị các frame đề xuất lọc bỏ với viền ngoài đỏ đậm để người dùng kiểm duyệt trực quan.
  - *Giải pháp đã chốt:* Cải tiến `check_object_difference` kiểm tra toàn diện các đối tượng lân cận (xe cộ, đồ vật, thiết bị) và mật độ nét chữ. Các frame trùng lặp hoặc mờ được gán `border_color = "red"`, `is_proposed_deletion = True` và giữ nguyên trên UI với khuôn viền đỏ đậm (`#ff5555`).
- **Thảo luận 8 (Về phân loại bối cảnh môi trường & Làm giàu Metadata BTC):**
  - *Yêu cầu từ User:* Đọc hậu cảnh để nhận diện bối cảnh chung (Nước/Biển, Cây cối/Thiên nhiên, Trong phòng/Studio, Đường phố/Giao thông, Sân vận động, hoặc Unknown). Keyframe BTC cần được đánh dấu viền xanh Cyan (`#8be9fd`) và làm giàu đầy đủ các trường metadata.
  - *Giải pháp đã chốt:*
    1. Xây dựng `TimelineSynchronizer.detect_scene_environment()` kết hợp dải màu HSV và tập nhãn YOLOv8.
    2. Xây dựng `TimelineSynchronizer.enrich_btc_metadata()` tự động tính độ nét Laplacian, màu sắc chủ đạo HSV, bối cảnh môi trường và số lượng vật thể cho keyframe BTC.
    3. Xây dựng `TimelineSynchronizer.build_unified_final_dataset()` xuất toàn bộ keyframe (cả BTC và System 1) ra `unified_multimodal_dataset.json` và `.csv`.

### Mốc 23/08/2026: Kiểm Duyệt Lọc Bỏ Sau Khi Merge Timeline BTC, Tái Cấu Trúc Ý Nghĩa Toàn Cú Máy & Suy Đoán BTC Context
- **Thảo luận 9 (Về quy trình kiểm duyệt lọc bỏ nghiêm ngặt chỉ sau khi Merge Timeline BTC):**
  - *Yêu cầu từ User:* Loại bỏ hoàn toàn việc đề xuất xóa sớm/tùy tiện ở bước trích xuất ban đầu. Việc kiểm duyệt và đề xuất lọc bỏ CHỈ ĐƯỢC PHÉP THỰC HIỆN SAU KHI MERGE toàn bộ timeline BTC và System 1 trên cùng một trục thời gian chung. Phải kiểm tra xem frame này trước đó đã có chưa, độ tương đồng thị giác phải rất cao ($\ge 0.92$) và không có khác biệt OCR / vật thể / bối cảnh mới đưa vào diện lọc bỏ hoặc chuyển thành Frame Cắt Nghĩa viền tím.
  - *Giải pháp đã chốt:*
    1. Trong `extract_video_keyframes_for_duration`: Giữ nguyên 100% keyframe trích xuất thô.
    2. Trong `TimelineSynchronizer.merge_and_deduplicate_timeline()`: Thực hiện gộp timeline BTC và System 1, kiểm tra lịch sử các frame đã xuất hiện trước đó. Nếu phát hiện trùng lặp cao ($\ge 0.92$) với frame trước đó: Ưu tiên giữ frame BTC / Anchor; frame trùng lặp chuyển thành Frame Cắt Nghĩa viền tím Neon (`#bd93f9`) kèm tag $\Delta t$, hoặc đánh dấu Đề Xuất Lọc Bỏ viền đỏ Đậm (`#ff5555`) nếu độ nét Laplacian thấp hơn rõ rệt ($< 0.70 \times \text{Anchor}$).
- **Thảo luận 12 (Về cơ chế hiển thị đa tag phân loại Multi-Badge & Tài liệu vận hành toàn diện):**
  - *Yêu cầu từ User:* Cho phép hiển thị đồng thời nhiều tag/badge phân loại xử lý trên mỗi thẻ khung hình; viết tài liệu tổng quan toàn bộ những gì đã làm và một tệp README hướng dẫn cách chạy, trình bày chi tiết thứ tự tuần tự các bước xử lý.
  - *Giải pháp đã chốt & triển khai:*
    1. Thiết kế cơ chế gom danh sách badges (`badges = []`), cho phép hiển thị đồng thời: `[Frame Cắt Nghĩa +Δt]`, `[Đã Làm Nét - Fallback]`, `[Chuyển Cảnh / Tiêu Đề]`, `[Đề Xuất Lọc Bỏ - ...]`, `[BTC-xử lý: Mật độ thông tin thấp]`.
    2. Thiết lập quy tắc ưu tiên màu viền ngoài: Đỏ (Lọc bỏ/BTC mật độ thấp) > Tím Neon (Frame Cắt Nghĩa) > Vàng Cam (Làm nét) > Xanh Cyan (BTC) > Xanh Lá (System 1).
    3. Xuất bản `SYSTEM_ARCHITECTURE_AND_PIPELINE_OVERVIEW.md` tổng kết toàn diện kiến trúc 5 bước, 8 trường metadata chuẩn tắc và bảng minh chứng định lượng 100% PASS.
    4. Xuất bản `RUN_AND_EXECUTION_GUIDE_README.md` hướng dẫn chi tiết cách khởi chạy 1-Click trên Windows/Kaggle và phân tích luồng xử lý tuần tự từ Bước 1 đến Bước 6.





