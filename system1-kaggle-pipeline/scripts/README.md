<!-- 
================================================================================
AGENT CONTEXT & PROTOCOL HEADER (DÀNH CHO CÁC AI AGENT KẾ NHIỆM)
- Tên tài liệu: system1-kaggle-pipeline/scripts/README.md (TẦNG 5B: Test Scripts Manual)
- Vai trò trong hệ thống: Sổ tay hướng dẫn sử dụng các kịch bản kiểm thử độc lập, Master CLI Runner và tiện ích đẩy dữ liệu Cloud.
- Ràng buộc quy tắc (Rules Compliance):
  * Rule 1: Giải thích rõ ràng mục tiêu ở đầu mỗi mục lớn.
  * Rule 2: Minh chứng thực nghiệm bắt buộc (Empirical Evidence).
  * Rule 11: Mô hình Quản trị 3 vai trò và kịch bản test case độc lập.
  * Rule 14: Biên soạn test case chạy lẻ trên dữ liệu thật.
  * Tone Constraint: Tuyệt đối KHÔNG dùng emoji/icon ở bất kỳ đâu.
- Tệp liên kết thượng nguồn (Upstream): plans/KEYFRAME_ENHANCEMENT_PLAN_AND_SUBAGENT_TASKS.md
- Tệp liên kết hạ nguồn (Downstream): EXECUTION_MILESTONES.md, test_output/
- Kịch bản kiểm thử tương ứng: python system1-kaggle-pipeline/scripts/validate_subagent_pipeline.py
================================================================================
-->

# Sổ Tay Hướng Dẫn Kịch Bản Kiểm Thử & Benchmark (System 1 Scripts)

Thư mục `system1-kaggle-pipeline/scripts/` đã được tinh giản và quy hoạch thành cấu trúc CLI thống nhất kèm các bài kiểm thử độc lập:

```text
system1-kaggle-pipeline/scripts/
├── README.md                          # Sổ tay hướng dẫn sử dụng (File này)
├── benchmark_runner.py                # TRÌNH ĐIỀU PHỐI ĐA NĂNG (Unified Master CLI Runner)
├── validate_subagent_pipeline.py      # KHUNG KIỂM ĐỊNH TỰ ĐỘNG 5 TIÊU CHUẨN (Validation Harness)
├── colab_upload_dataset.py            # Tiện ích đẩy dữ liệu từ Google Drive sang Kaggle Dataset
└── steps/                             # Thư mục con chứa các kịch bản kiểm thử chi tiết
    ├── step1_keyframes.py             # Pipeline V1: Trích xuất keyframe và đo độ sắc nét
    ├── step2_embeddings.py            # Pipeline V1: Ma trận vector nhúng và tính toán Cosine
    ├── step3_ocr.py                   # Pipeline V1: Phát hiện vật thể và bóc tách chân trang
    ├── step4_db_search.py             # Pipeline V1: Xây dựng SQLite FTS5 và tìm kiếm toàn văn
    ├── test_step1_event_keyframes.py  # Nâng cấp: Keyframe theo sự kiện vật thể & Crowd Suppression (100% PASS)
    ├── test_step2_video_ocr_dedup.py  # Nâng cấp: Video OCR phân vùng & Khử trùng lặp Jaccard (100% PASS)
    ├── test_step3_asr_timestamp_qa.py # Nâng cấp: Video QA ASR FTS5 tra cứu theo timestamp (100% PASS)
    ├── test_step4_genre_classifier.py # Nâng cấp: Phân loại thể loại video từ metadata & RRF (100% PASS)
    └── test_step5_timeline_merge_dedup.py # Nâng cấp: Hợp nhất timeline BTC-Self & Frame Cắt Nghĩa viền tím (100% PASS)
```

---

## 1. Trình Điều Phối Thống Nhất (`benchmark_runner.py`)

Thay vì phải chạy nhiều file script rời rạc, bạn chỉ cần sử dụng **`benchmark_runner.py`** với tham số `--mode`:

### 1.1. Chạy 4 Bài Kiểm Thử Dữ Liệu Thật (`--mode steps`)
Chạy toàn bộ 4 bước kiểm thử lõi (Keyframes, Ma trận Vector, Nhãn vật thể, SQLite FTS5) trên dữ liệu nhị phân thật:
```bash
python system1-kaggle-pipeline/scripts/benchmark_runner.py --mode steps
```

### 1.2. Cắt Cú Máy & Lấy Mẫu Keyframe Trực Tiếp Từ Video MP4 (`--mode raw_video`)
Giải mã trực tiếp tệp video MP4 thô và phân tách cú máy:
```bash
# Quét 1,500 frames đầu (~50 giây) của video L21_V001
python system1-kaggle-pipeline/scripts/benchmark_runner.py --mode raw_video --video L21_V001 --frames 1500

# Quét toàn bộ video (đặt --frames 0)
python system1-kaggle-pipeline/scripts/benchmark_runner.py --mode raw_video --video L21_V001 --frames 0
```

### 1.3. Chạy Benchmark Đối Chiếu 10 Video Mẫu Với BTC (`--mode 10_videos`)
Xử lý 10 video mẫu (5 video đầu: `L21_V001` - `L21_V006`, 5 video cuối: `L21_V027` - `L21_V031`) và lưu toàn bộ kết quả vào thư mục riêng `test_output/side_by_side_benchmark/`:
```bash
python system1-kaggle-pipeline/scripts/benchmark_runner.py --mode 10_videos
```

---

## 2. Các Kịch Bản Kiểm Thử Độc Lập Cho 5 Phân Hệ Nâng Cấp (Rule 14)

Các kịch bản kiểm thử này có thể chạy độc lập từng file để xác nhận tính chính xác của từng module thuật toán:

```bash
# Step 1: Kiểm thử bắt mốc vào/ra vật thể và ức chế đám đông
python system1-kaggle-pipeline/scripts/steps/test_step1_event_keyframes.py

# Step 2: Kiểm thử khử trùng lặp OCR và phân vùng chân trang
python system1-kaggle-pipeline/scripts/steps/test_step2_video_ocr_dedup.py

# Step 3: Kiểm thử tra cứu Video QA theo mốc giây tiếng Việt có/không dấu
python system1-kaggle-pipeline/scripts/steps/test_step3_asr_timestamp_qa.py

# Step 4: Kiểm thử phân loại thể loại video từ metadata và gán trọng số RRF
python system1-kaggle-pipeline/scripts/steps/test_step4_genre_classifier.py

# Step 5: Kiểm thử hợp nhất timeline BTC-Self, đếm 'Nhãn x Số lượng' & Frame Cắt Nghĩa viền tím
python system1-kaggle-pipeline/scripts/steps/test_step5_timeline_merge_dedup.py
```

---

## 3. Khung Kiểm Định Tự Động Toàn Diện Cho Sub-Agents (`validate_subagent_pipeline.py`)

Chạy kiểm tra tự động 5 tiêu chuẩn vàng trước khi bàn giao:
```bash
python system1-kaggle-pipeline/scripts/validate_subagent_pipeline.py
```
