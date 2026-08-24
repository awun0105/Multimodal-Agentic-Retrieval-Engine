# Sổ Tay Danh Mục Lỗi, Nguyên Nhân & Giải Pháp Phòng Thủ Toàn Diện (Error Prevention & Edge Cases)

Tài liệu này ghi nhận toàn bộ các lỗi tiềm ẩn, nguyên nhân gốc rễ (Root Cause Analysis), các giải pháp kiến trúc phòng thủ (Defensive Architecture Patterns) và ma trận kiểm thử biên (Edge Case Test Matrix) được triển khai trên hệ thống AIC 2026 Multimodal Retrieval Engine.

---

## 1. Danh Mục Các Lỗi Đã Rà Soát & Xử Lý Triệt Để

### Lỗi 1: `AttributeError: 'float' object has no attribute 'keys'`
- **Biểu hiện:** Khi gọi `TimelineSynchronizer.merge_and_deduplicate_timeline()`, hệ thống báo lỗi khi duyệt `prev_item.get("objects_dict", {}).keys()`.
- **Nguyên nhân gốc rễ:** 
  * Dữ liệu được nạp từ tệp CSV qua thư viện `pandas` (`benchmark_summary.csv`).
  * Khi một trường dữ liệu (`objects_dict`, `detected_classes`) bị rỗng trong CSV, Pandas tự động gán giá trị `np.nan` (kiểu `float`).
  * Hàm `.get("objects_dict", {})` tìm thấy key `"objects_dict"` với giá trị `float('nan')` nên không trả về `{}` mặc định. Khi gọi `.keys()` trên giá trị `float('nan')`, Python ném ngoại lệ `AttributeError`.
- **Giải pháp phòng thủ:**
  * Xây dựng hàm `TimelineSynchronizer.safe_extract_object_keys(item)` kiểm tra chặt chẽ `isinstance(obj_dict, dict)` trước khi truy xuất `.keys()`.
  * Xử lý đa năng: Hỗ trợ cả trường hợp chuỗi đại diện từ CSV (`"{'person': 2}"` hoặc `"['person', 'car']"` qua `ast.literal_eval`), danh sách `list/set/tuple` và bóc tách từ chuỗi `objects_and_counts`.
  * Làm sạch toàn diện tệp CSV tại `_load_cached_self_keyframes` bằng cách lọc `pd.isna(v) -> None`.

---

### Lỗi 2: `SyntaxError: closing parenthesis ')' does not match opening parenthesis '['`
- **Biểu hiện:** Dòng 714 trong `interactive-test-app/app.py` bị lỗi cú pháp khi khởi động ứng dụng.
- **Nguyên nhân gốc rễ:** Lệnh list comprehension có 3 dấu ngoặc đóng `0.0)))` trong khi chỉ mở 2 dấu ngoặc `float(` và `.get(`.
- **Giải pháp:** Chuẩn hóa lại thành:
  ```python
  s_in_slot = [s for s in self_list if t_start <= float(s.get("pts_time_sec", 0.0)) < t_end]
  ```

---

### Lỗi 3: `NameError: name 'parse_duration_limit' is not defined`
- **Biểu hiện:** Hàm `render_side_by_side_comparison()` không tìm thấy định nghĩa hàm phân giải thời lượng.
- **Nguyên nhân gốc rễ:** Các hàm tiện ích `parse_duration_limit()`, `_load_cached_self_keyframes()`, và `_save_cached_self_keyframes()` chưa được đặt trong phạm vi hoạt động của module.
- **Giải pháp:** Định nghĩa rõ ràng 3 hàm tiện ích với cơ chế tự động giới hạn `60s`, `180s`, `300s`, `full` và nạp/lưu cache CSV.

---

### Lỗi 4: Xử lý chuỗi `'nan'`, `'none'`, `float('nan')` trong các trường văn bản
- **Biểu hiện:** Trường OCR, bối cảnh, hoặc màu sắc hiển thị chuỗi `"nan"` hoặc `"None"` trên giao diện người dùng.
- **Nguyên nhân gốc rễ:** Lệnh ép kiểu `str(val)` đối với `float('nan')` biến giá trị rỗng thành chuỗi ký tự `"nan"`.
- **Giải pháp phòng thủ:**
  * Xây dựng hàm `TimelineSynchronizer.clean_text_field(val)` tự động kiểm tra `math.isnan(val)` và lọc bỏ các chuỗi `"nan"`, `"none"`, `"null"`, `"undefined"`.

---

### Lỗi 5: Xung đột Port mạng & Tiến trình chạy ngầm (Port 7860 Collision)
- **Biểu hiện:** Báo lỗi `OSError: [Errno 10048] Address already in use` khi khởi động lại Gradio.
- **Nguyên nhân gốc rễ:** Tiến trình Python trước đó chưa giải phóng hoàn toàn socket TCP trên cổng 7860/7861.
- **Giải pháp phòng thủ:**
  * Tích hợp cơ chế quét PID chiếm cổng qua lệnh `netstat -ano` và tự động giải phóng cổng bằng `taskkill /F /PID <pid>` trong `launcher.py`.
  * Hỗ trợ phím tắt `Ctrl + C` để lập tức ngắt tiến trình và dọn dẹp bộ nhớ RAM.

---

## 2. Các Hàm Kiến Trúc Phòng Thủ (Defensive Utilities Reference)

```python
# 1. Trích xuất nhãn vật thể an toàn tuyệt đối
TimelineSynchronizer.safe_extract_object_keys(item: dict) -> set[str]

# 2. Làm sạch chuỗi văn bản chống NaN/None
TimelineSynchronizer.clean_text_field(val: Any) -> str

# 3. Ép kiểu float an toàn chống NaN/Inf/String
TimelineSynchronizer.safe_float(val: Any, default: float = 0.0) -> float

# 4. Định dạng và đếm số lượng vật thể tiếng Việt
TimelineSynchronizer.format_object_counts(detected_classes) -> tuple[str, dict[str, int]]
```

---

## 3. Ma Trận Kiểm Thử Biên & Dữ Liệu Bẩn (Edge Case Test Matrix)

Kịch bản kiểm thử độc lập [system1-kaggle-pipeline/scripts/steps/test_step5_timeline_merge_dedup.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/steps/test_step5_timeline_merge_dedup.py) đã được bổ sung bài test `[TEST 7]` kiểm tra các điều kiện khắc nghiệt:

| Tình Huống Kiểm Thử (Edge Case) | Dữ Liệu Đầu Vào | Kết Quả Xử Lý | Trạng Thái |
| :--- | :--- | :--- | :--- |
| **Trường `objects_dict` là `float('nan')`** | `{"objects_dict": float("nan")}` | Bóc tách trả về `set()` an toàn, không ném ngoại lệ | **ĐẠT (PASS)** |
| **Trường `detected_classes` là chuỗi JSON** | `{"detected_classes": "['person', 'car']"}` | Tự động parse thành `{'person': 1, 'car': 1}` | **ĐẠT (PASS)** |
| **Trường `pts_time_sec` là `float('nan')`** | `{"pts_time_sec": float("nan")}` | Tự động gán mốc `0.0s`, sắp xếp đúng thứ tự | **ĐẠT (PASS)** |
| **Trường `sharpness_score` là chuỗi số** | `{"sharpness_score": "520.5"}` | Ép kiểu an toàn thành `520.5` | **ĐẠT (PASS)** |
| **Trường `ocr_text` là `"nan"`** | `{"ocr_text": "nan"}` | Làm sạch thành `""` rỗng, không hiển thị rác | **ĐẠT (PASS)** |
| **Gộp mốc sát ranh giới $|\Delta t| = 0.05\text{s}$** | Frame 1: 4.002s, Frame 2: 4.020s | Gộp chính xác 2 frame thành 1 bản ghi | **ĐẠT (PASS)** |

---

## 4. Kết Quả Xác Thực Thực Nghiệm

Toàn bộ 5 bộ kiểm thử độc lập (Step 1-5) đã được thực thi tự động và đạt **100% ALL PASS**. Ứng dụng Web Studio hoàn toàn ổn định và sẵn sàng vận hành.
