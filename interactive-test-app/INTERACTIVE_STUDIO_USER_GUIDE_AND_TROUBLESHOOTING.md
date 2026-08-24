# HƯỚNG DẪN TOÀN DIỆN VẬN HÀNH & XỬ LÝ SỰ CỐ: INTERACTIVE COCKPIT STUDIO (AIC 2026)

Tài liệu này cung cấp hướng dẫn chi tiết về cấu trúc mã nguồn, cơ chế vận hành, hướng dẫn khởi động 1-Click, và phương pháp khắc phục toàn bộ các lỗi thường gặp khi chạy Visual Cockpit Studio trên máy tính cá nhân hoặc môi trường Cloud/Kaggle.

---

## 1. Bản Đồ 5 Phân Hệ Trực Quan Hóa (Tabs Matrix)

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                        AIC 2026 RETRIEVAL & BENCHMARK STUDIO (KIẾN TRÚC 5 TẦNG)                        │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ TAB 1: SO SÁNH TRỰC QUAN SIDE-BY-SIDE (BAN TỔ CHỨC vs. SYSTEM 1 TỰ XỬ LÝ)                              │
│   - Đối chiếu trực quan theo từng Slot thời gian 3 giây trên trục Timeline.                             │
│   - Nửa Trái: Keyframe Ban Tổ Chức (BTC) + Thẻ cảnh báo [BTC-xử lý] khi mật độ thông tin thấp.         │
│   - Nửa Phải: Keyframe System 1 + Thẻ Đa Nhãn (Frame Cắt Nghĩa, Đã Làm Nét, Chuyển Cảnh/Tiêu Đề).      │
│   - Thẻ Song Ngữ: [BẢN MIÊU TẢ TIẾNG VIỆT] (thuần tự nhiên) + [DỊCH & LÀM GIÀU EN CHO SIGLIP].        │
│   - Bóc Tách Vật Thể: Định lượng số lượng (N = ...) và màu sắc trang phục / thân xe (áo đen, xe đỏ...).│
│   - Con Trỏ Địa Chỉ Nhớ (Virtual Pointer): Frame Cắt Nghĩa dùng chung ảnh Anchor -> Tiết kiệm 100% đĩa.│
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ TAB 2: QUẢN LÝ LƯU TRỮ & DỮ LIỆU ĐÃ TRÍCH XUẤT (PERSISTENCE & STORAGE HUB)                             │
│   - Thống kê toàn bộ video đã xử lý, số shot bắt được, độ nét trung bình, dung lượng ảnh WebP.         │
│   - Xuất dữ liệu hợp nhất sang JSON và CSV theo chuẩn hợp đồng nộp bài thi AIC 2026.                   │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ TAB 3: BẢNG SO SÁNH ĐA PHƯƠNG THỨC & KẾT QUẢ XỬ LÝ CHI TIẾT (MULTIMODAL BENCHMARK)                     │
│   - Bóc tách kết quả OCR 2-Tier (tiêu đề chân trang vs văn bản trong khung hình).                     │
│   - Ma trận so sánh Vision Embedding: SigLIP SO400M (1152d) vs ViSigLIP-OT (768d).                    │
│   - Luồng làm giàu truy vấn văn hóa bản địa trung thực (Faithful Query Enrichment < 0.5ms).            │
│   - Tra cứu Video QA ASR Speech-to-Text < 2ms.                                                         │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ TAB 4: TÌM KIẾM TRỰC QUAN KIS & VIDEO QA (SYSTEM 2 DUAL-STREAM HYBRID RETRIEVAL)                       │
│   - Tìm kiếm kết hợp: Dense Vector FAISS + Sparse FTS5 BM25 + ASR Timestamp Search.                    │
│   - Hỗ trợ On/Off linh hoạt: Chế độ 1 mô hình nhanh (<20ms) hoặc Chế độ Song song Dual-Model (<45ms).  │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ TAB 5: STUDIO TÙY CHỈNH THAM SỐ ĐẦU VÀO (SYSTEM 1 PARAMETER TUNING)                                    │
│   - Tùy chỉnh trực tiếp: Ngưỡng cắt cảnh Histogram, Bộ lọc độ nét Laplacian, Tỷ lệ nén WebP.          │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Hướng Dẫn Khởi Động Ứng Dụng

### Cách 1: Khởi Động Trực Tiếp 1-Click (Khuyến Nghị Tuyệt Đối)
Nhấp đúp chuột vào tập tin:
[start_interactive_test_app.bat](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/start_interactive_test_app.bat)

*Hệ thống sẽ tự động thực hiện 3 bước ngầm:*
1. Quét và giải phóng các tiến trình zombie đang chiếm cổng 7860/7861.
2. Khởi chạy máy chủ Web Studio với môi trường Python tối ưu.
3. Tự động bật tab trình duyệt tại địa chỉ `http://127.0.0.1:7860`.

### Cách 2: Khởi Động Bằng Dòng Lệnh (Terminal / PowerShell)
```powershell
python interactive-test-app/app.py
```

### Cách 3: Bảng Điều Khiển Nâng Cao (Menu Launcher)
```powershell
python interactive-test-app/launcher.py
```

---

## 3. Khắc Phục Toàn Diện Các Lỗi Thường Gặp (Troubleshooting Guide)

### Lỗi 1: Cổng 7860 Đang Bị Chiếm Dụng (Port 7860 Already In Use)
- **Hiện tượng:** Khi chạy hiện thông báo `[Errno 10048] Only one usage of each socket address is normally permitted`.
- **Cơ chế tự động khắc phục của Studio:**
  * Mã nguồn trong [interactive-test-app/app.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/interactive-test-app/app.py) đã được tích hợp cơ chế tự động tìm PID đang chiếm cổng và ra lệnh giải phóng tức thì (`kill_process_by_pid`).
  * Nếu cổng 7860 vẫn bị khóa cứng bởi tiến trình hệ thống khác, Studio sẽ tự động chuyển sang cổng tiếp theo (`http://127.0.0.1:7861` hoặc `7862`) và tự động mở trình duyệt tương ứng.
- **Giải phóng thủ công bằng 1 dòng lệnh:**
  ```powershell
  python -c "import subprocess; [subprocess.run(['taskkill', '/F', '/PID', line.strip().split()[-1]], stdout=subprocess.PIPE, stderr=subprocess.PIPE) for line in subprocess.check_output(['netstat', '-ano', '-p', 'tcp'], errors='ignore').splitlines() if ':7860 ' in line and 'LISTENING' in line]"
  ```

### Lỗi 2: Trình Duyệt Không Tự Động Mở
- **Hiện tượng:** Terminal báo máy chủ đã sẵn sàng nhưng trình duyệt không tự bật.
- **Cách xử lý:** Mở trình duyệt bất kỳ (Chrome, Edge, Firefox, Cốc Cốc) và gõ địa chỉ:
  **`http://127.0.0.1:7860`**

### Lỗi 3: Thiếu Thư Viện Cần Thiết
- **Hiện tượng:** Báo lỗi `ModuleNotFoundError: No module named 'gradio'` hoặc `'ultralytics'`.
- **Cách xử lý:** Chạy lệnh cài đặt bổ sung:
  ```powershell
  pip install gradio opencv-python ultralytics pandas pillow
  ```

---

## 4. Danh Mục Các Module & Tập Tin Trong Phân Hệ

| Tập Tin | Vai Trò | Đường Dẫn |
| :--- | :--- | :--- |
| **`app.py`** | Giao diện Studio chính, xây dựng bằng Gradio Blocks với 5 Tab trực quan hóa. | [interactive-test-app/app.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/interactive-test-app/app.py) |
| **`launcher.py`** | Trình quản trị vòng đời ứng dụng (Start, Stop, Restart, Port Reset). | [interactive-test-app/launcher.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/interactive-test-app/launcher.py) |
| **`start_interactive_test_app.bat`** | File batch 1-Click tự động dọn port và mở trình duyệt ngay lập tức. | [start_interactive_test_app.bat](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/start_interactive_test_app.bat) |
| **`run_all_system1_step_tests.bat`** | Bộ script kiểm thử tự động toàn bộ 6 bước độc lập (100% ALL PASS). | [run_all_system1_step_tests.bat](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/run_all_system1_step_tests.bat) |
| **`README.md`** | Tài liệu giới thiệu tóm tắt phân hệ. | [interactive-test-app/README.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/interactive-test-app/README.md) |
| **`ERROR_PREVENTION_AND_EDGE_CASES_README.md`** | Sổ tay xử lý dữ liệu biên và phòng ngừa lỗi trích xuất. | [interactive-test-app/ERROR_PREVENTION_AND_EDGE_CASES_README.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/interactive-test-app/ERROR_PREVENTION_AND_EDGE_CASES_README.md) |
