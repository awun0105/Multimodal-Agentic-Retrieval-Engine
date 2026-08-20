# Kế hoạch tích hợp tính năng OCR (Nhận diện chữ viết)

Tài liệu này đề xuất thiết kế và kế hoạch chi tiết để tích hợp tính năng tìm kiếm văn bản OCR trên ảnh keyframe vào bộ máy tìm kiếm của dự án.

## Đánh giá hiện trạng & Phát hiện nghiên cứu

1. **system1 đã có cấu trúc dữ liệu cho OCR**:
   - `sqlite_builder.py` đã định nghĩa các bảng `ocr` và `text_documents` nhưng chưa được đóng gói hoàn tất vào tệp `runtime.sqlite` phát hành do thiếu tệp parquet đầu vào ở Phase00/01.
   - `sqlite_builder.py` đã hỗ trợ bảng ảo FTS5 `text_documents_fts` cho việc tìm kiếm toàn văn, lưu trữ cột `normalized_text` và `normalized_no_diacritics` (dịch không dấu tiếng Việt).
2. **mvp-app chưa tích hợp OCR**:
   - Tệp `db.py` hiện tại chỉ truy vấn 3 bảng chính: `videos`, `keyframes`, và `detections`.
   - Giao diện `app.py` hiện tại chỉ hỗ trợ hiển thị ảnh tĩnh, chưa có tính năng vẽ khung bounding box cho chữ viết nhận diện được.

---

## Các Quyết Định Thiết Kế & Cấu Hình (Đã Align với User)

1. **Nhánh thực hiện (Branch)**:
   - Toàn bộ các thay đổi và cập nhật mã nguồn sẽ được thực hiện trên một nhánh Git mới có tên: `monolith-mvp-app-with-ocr`.
2. **Chế độ tìm kiếm**: 
   - Hỗ trợ cả hai chế độ:
     *   Chế độ bật/tắt (Toggle) độc lập giữa Tìm kiếm ảnh (CLIP) và Tìm kiếm chữ (OCR).
     *   Chế độ Tìm kiếm kết hợp (Hybrid Search) phối hợp cả hai.
3. **Trọng số kết hợp (Fusion Weight)**:
   - Trọng số mặc định là **0.5 - 0.5** (50% điểm ảnh CLIP và 50% điểm chữ OCR).
   - Có thể điều chỉnh trực tiếp trên giao diện UI thông qua thanh trượt (Slider).
4. **Keyframes xử lý (Quét OCR)**:
   - Tiến trình OCR sẽ quét trực tiếp trên **tập hợp keyframe gốc (raw keyframes)** thay vì chỉ quét trên các keyframe đã được rút gọn/nén của release.
   - *Cơ chế liên kết*: Dữ liệu chữ quét từ các keyframe gốc sẽ được nhóm hoặc ánh xạ (mapping) sang keyframe đại diện tương ứng trong cơ sở dữ liệu runtime để bộ máy tìm kiếm có thể truy vấn chính xác.
5. **Trực quan hóa Bounding Box**:
   - Nếu dữ liệu OCR đầu vào có đi kèm tọa độ khung chữ, hệ thống sẽ hỗ trợ vẽ trực tiếp lên ảnh chi tiết bằng `gr.AnnotatedImage`. Nếu dữ liệu thô chỉ có chữ, hệ thống sẽ chỉ hiển thị nội dung chữ dưới dạng text.
6. **Đẩy và cập nhật dữ liệu (Push & Data Updates)**:
   - *Mã nguồn (Code)*: Sẽ được commit trên nhánh `monolith-mvp-app-with-ocr` và push lên remote origin (GitHub) sau khi hoàn tất kiểm thử.
   - *Dữ liệu lớn (Large Data)*: Các tệp cơ sở dữ liệu SQLite cập nhật hoặc dữ liệu chữ quét được (OCR text) sẽ được lưu trữ và cập nhật trực tiếp tại local workspace (ở thư mục data/cache) hoặc đẩy lên kho lưu trữ chia sẻ Hugging Face (`AIC26_release` / `AIC26_raw` Dataset) theo quy chuẩn của dự án, hoàn toàn **không** commit các tệp cơ sở dữ liệu này lên Git để tránh quá tải repository.

---

## Đề xuất các thay đổi (Proposed Changes)

### 1. Phân hệ Tiền xử lý (Preprocessing - `system1`)

#### [MODIFY] [sqlite_builder.py](../../../system1/src/system1/db/sqlite_builder.py)
- Đảm bảo bảng `text_documents` và chỉ mục FTS5 `text_documents_fts` được tự động khởi tạo và nạp dữ liệu OCR từ các tệp parquet đầu vào (`ocr.parquet` hoặc `text_documents.parquet`) nếu có.
- Nếu không có dữ liệu đầu vào, tự động khởi tạo bảng trống để tránh lỗi SQL `no such table` ở phía runtime.

---

### 2. Ứng dụng Runtime (Giao diện & Tìm kiếm - `mvp-app`)

#### [MODIFY] [db.py](../../../mvp-app/db.py)
- Thêm phương thức `_search_ocr_fts(self, query_text: str)` để thực hiện tìm kiếm từ khóa trên bảng `text_documents_fts` bằng SQLite FTS5.
- Cập nhật hàm `search_by_text` để thực hiện hợp nhất kết quả (Score Fusion) giữa điểm số tương đồng vector của CLIP và điểm số BM25 của FTS5.
- Cập nhật hàm `get_keyframe_details` để truy vấn thêm nội dung chữ viết và các tọa độ khung chữ (nếu có).

#### [MODIFY] [app.py](../../../mvp-app/app.py)
- Chuyển component `gr.Image` hiển thị ảnh chi tiết sang `gr.AnnotatedImage` để hỗ trợ vẽ bounding box và gắn nhãn chữ viết trực quan.
- Thêm phần hiển thị toàn bộ nội dung chữ OCR quét được dưới dạng Markdown trong bảng metadata.
- (Tùy chọn) Bổ sung thanh trượt điều chỉnh trọng số tìm kiếm giữa Vector và OCR trên giao diện.

---

## Kế hoạch Xác minh (Verification Plan)

### Kiểm thử Thủ công (Manual Verification)
1. Chạy thử nghiệm với các từ khóa tiếng Việt đặc thù chứa trong biển báo hoặc chữ trên màn hình (ví dụ: *"Cảnh báo sạt lở"*).
2. Kiểm tra xem kết quả chính xác có được xếp hạng lên Top 1 hay không.
3. Xác minh tính năng vẽ khung bounding box (nếu có) trên ảnh chi tiết và bảng văn bản hiển thị đầy đủ, không bị lỗi hiển thị.
4. Kiểm tra sự thay đổi thứ hạng khi điều chỉnh các trọng số tìm kiếm khác nhau.
