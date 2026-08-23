# HƯỚNG DẪN ĐỌC HIỂU SẢN PHẨM & LUỒNG THỰC THI (PRODUCT & EXECUTION GUIDE)

Tài liệu này giúp bạn nắm bắt nhanh toàn bộ **Kiến trúc, Luồng thông tin (Data Flow), Cách đọc hiểu từng File mã nguồn** và **Cách chạy trực tiếp sản phẩm** mảng Embedding (Người 1) trên nhánh `dev`.

---

## 1. Sơ Đồ Luồng Thông Tin (Data Flow Chart)

Khi bạn hoặc người dùng nhập vào một câu tìm kiếm bằng Tiếng Việt (ví dụ: `"người mặc áo đỏ trên khán đài"`), luồng xử lý của sản phẩm diễn ra qua 5 bước liên hoàn như sau:

```text
[BƯỚC 1: INPUT]
  └── Câu truy vấn Tiếng Việt từ User: "người mặc áo đỏ trên khán đài"
         │
         ▼
[BƯỚC 2: TRANSLATION API] ---> (File: system1/research/embedding/translator.py)
  └── Dịch Tiếng Việt -> Tiếng Anh: "People wearing red shirts in the stands"
         │
         ▼
[BƯỚC 3: PROMPT OPTIMIZER SUB-AGENT] ---> (File: system1/research/embedding/prompt_optimizer.py)
  └── Làm giàu Prompt với bối cảnh Thể thao + Hiện màn hình XÁC NHẬN với User:
      "People wearing red shirts in the stands, sports competition photo"
         │
         ▼
[BƯỚC 4: VECTOR EXTRACTION & L2 NORM] ---> (File: system1/research/embedding/extractor.py)
  └── Biến câu Prompt thành Vector 1D NumPy array shape (512,) và chuẩn hóa L2 length = 1.0
         │
         ▼
[BƯỚC 5: VECTOR SEARCH VỚI ĐỊNH DẠNG TRUY NGƯỢC CHUẨN (TRACEABILITY)] ---> (File: system1/research/embedding/test_real_retrieval.py)
  └── So sánh Cosine Similarity với 1,896 ảnh Keyframe thật trích xuất từ 10 folder video trong `Keyframes_L26_c.zip`
  └── Đọc ánh xạ metadata từ `data/benchmark_samples/metadata_map.json`
  └── Xuất ra TOP 5 Khung hình kèm thông tin truy ngược đầy đủ (Video ID: L26_V202, Frame ID: 034, Keyframe ID: L26_V202/034)
```

---

## 2. Hướng Dẫn Đọc Hiểu Từng File Mã Nguồn

Dưới đây là danh sách các file cốt lõi và cách đọc hiểu chúng:

### 📄 1. File `inspect_data.py` (Trích xuất Dữ liệu Mẫu Giữ Cấu Trúc Video)
- **Vị trí:** `scripts/inspect_data.py`
- **Nhiệm vụ:** Soi file zip `Keyframes_L26_c.zip`, trích xuất 1,896 keyframes thuộc 10 thư mục video (`L26_V200` đến `L26_V209`) và lưu file ánh xạ `metadata_map.json`.

### 📄 3. File `interactive_cockpit.py` (Ứng Dụng Web Interactive Cockpit)
- **Vị trí:** `system1/research/embedding/interactive_cockpit.py`
- **Nhiệm vụ:** Chạy Web Server giao diện **Human-in-the-Loop Cockpit (Dark mode)** tại `http://localhost:8000`.
- **Tính năng nổi bật:**
  1. **Ô Tìm Kiếm & Tự Động Tối Ưu Prompt:** Nhập tiếng Việt -> Dịch -> Tối ưu prompt -> Hiện tốc độ latency (< 100ms).
  2. **Lưới Ảnh 1,896 Keyframes:** Hiển thị ảnh kèm `Video ID`, `Frame ID`, `Score`.
  3. **Kiểm Duyệt Nhanh (Verified Checkbox):** Tích chọn các khung hình chính xác.
  4. **Timeline Modal:** Click nút `🎬 Timeline` để xem 10 ảnh xung quanh mốc thời gian đó.
  5. **One-Click CSV Export:** Bấm nút **"Xuất File Nộp Bài CSV"** để tạo file `submission_aic2026.csv` nộp cho BTC.

### 📄 5. File `report.md` (Báo cáo kết quả thử nghiệm)
- **Vị trí:** `system1/research/embedding/report.md`
- **Nhiệm vụ:** Tổng hợp các bảng so sánh chỉ số giữa các mô hình CLIP vs SigLIP vs BGE-Visual.

---

## 3. Cách Lệnh Chạy Trực Tiếp Để Xem Sản Phẩm Chạy (Live Demo)

Để tận mắt chứng kiến sản phẩm hoạt động trên máy tính của bạn, hãy mở Terminal trong IDE và gõ dòng lệnh sau:

```powershell
$env:PYTHONIOENCODING="utf-8"; uv run --project system1 python system1/research/embedding/test_real_retrieval.py
```

### Output kỳ vọng bạn sẽ thấy trên màn hình:
1. Chương trình thông báo load 100 ảnh keyframes thật từ `data/benchmark_samples/`.
2. Hệ thống mã hóa 100 ảnh thành Ma trận Vector `(100, 512)` chỉ trong ~31 ms.
3. Sub-Agent nhận câu hỏi Tiếng Việt -> Dịch Tiếng Anh -> Tối ưu Prompt Thể thao.
4. Hệ thống in ra danh sách **TOP 5 KHUNG HÌNH (KEYFRAMES)** khớp nhất kèm điểm tương đồng Cosine Similarity!
