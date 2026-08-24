# KẾ HOẠCH QUẢN TRỊ KIẾN TRÚC MODULE HÓA & LỘ TRÌNH PHÁT TRIỂN STUDIO (AIC 2026)

Tài liệu này được lập theo **Quy Tắc 14 (Sub-Agent Plan Governance)** và **Quy Tắc 11 (Task Fragmentation & Model Delegation)**, phân rã toàn diện phân hệ **Interactive Cockpit Studio** thành các module độc lập, cắm-rút (Plug-and-Play) nhằm phục vụ các lần nâng cấp, kiểm thử và chuyển giao đa Agent mà không gây xung đột mã nguồn.

---

## 1. Mục Tiêu & Chiến Lược Module Hóa (Modular Decoupling Strategy)

### 1.1. Thực Trạng Hiện Tại
- Tệp `interactive-test-app/app.py` hiện đóng vai trò tất-cả-trong-một (Monolithic): vừa dựng Gradio UI, vừa xử lý logic bóc tách màu HSV, sinh câu miêu tả song ngữ, đồng bộ timeline và xuất file.
- **Thách thức:** Khi nhiều Agent hoặc tính năng mới cùng can thiệp (ví dụ nâng cấp VLM Re-ranking hoặc thêm filter âm thanh ASR), nguy cơ xảy ra lỗi cú pháp hoặc xung đột biến toàn cục tăng cao.

### 1.2. Kiến Trúc Mục Tiêu (3-Tier Layered Architecture)

```text
interactive-test-app/
├── app.py                             <- Điểm nhập (Entrypoint): Khởi tạo Gradio Blocks & ráp 5 Tabs
├── components/                        <- TẦNG 1: GIAO DIỆN & SỰ KIỆN TỪNG TAB (UI COMPONENTS)
│   ├── tab1_side_by_side.py           <- Tab 1: So sánh trực quan Side-by-Side & Timeline Tracker
│   ├── tab2_storage_hub.py            <- Tab 2: Quản lý lưu trữ, thống kê WebP & xuất JSON/CSV
│   ├── tab3_multimodal_matrix.py      <- Tab 3: Bảng so sánh đa phương thức Steps 1 - 6
│   ├── tab4_hybrid_search.py          <- Tab 4: Tìm kiếm KIS Vector SigLIP + FTS5 BM25
│   └── tab5_parameter_tuning.py       <- Tab 5: Studio tùy chỉnh tham số System 1
├── services/                          <- TẦNG 2: NGHIỆP VỤ & XỬ LÝ DỮ LIỆU (BUSINESS SERVICES)
│   ├── timeline_service.py            <- Đồng bộ hóa mốc thời gian, kế thừa ngữ cảnh BTC
│   ├── appearance_service.py          <- Bóc tách màu sắc cá thể HSV (áo đen, áo trắng, xe đỏ...)
│   ├── caption_service.py             <- Sinh cặp miêu tả tự nhiên song ngữ (Fact-Grounded VI/EN)
│   └── export_service.py              <- Xuất bộ dữ liệu hợp nhất chuẩn nộp bài AIC 2026
├── templates/                         <- TẦNG 3: MẪU GIAO DIỆN & ĐỊNH DẠNG HTML (HTML TEMPLATES)
│   ├── card_templates.py              <- Mẫu thẻ Keyframe BTC (cyan), System 1 (tím/đỏ/lá), Badge
│   └── theme_tokens.py                <- CSS tokens, Dark Mode palette, hover micro-animations
└── plans/                             <- SỔ CÁI KẾ HOẠCH & NHẬT KÝ THẢO LUẬN SUB-AGENT (RULE 14)
    └── STUDIO_MODULAR_ARCHITECTURE_AND_EXPANSION_PLAN.md
```

---

## 2. Mô Hình Quản Trị Ba Vai Trò (Three-Role Agent Framework - Rule 11)

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                        MÔ HÌNH QUẢN TRỊ 3 VAI TRÒ CHO PHÂN HỆ STUDIO (RULE 11)                         │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 1. ORCHESTRATION AGENT (Agent Quản Lý Phân Mục):                                                       │
│   - Quản trị luồng dữ liệu giữa Gradio Blocks và các Service nghiệp vụ.                                │
│   - Định nghĩa Data Contracts JSON chuẩn hóa giữa các Tab.                                             │
│   - Xử lý lỗi ngoại lệ (Fault-Tolerance) và tự động giải phóng port 7860/7861.                        │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 2. EXECUTION AGENT (Agent Thực Hiện):                                                                  │
│   - Viết mã nguồn độc lập cho từng Component UI trong `components/` và Service trong `services/`.      │
│   - Tối ưu hóa thuật toán HSV Color Appearance và truy vấn FAISS < 15ms.                               │
│   - Tuân thủ quy chuẩn NO EMOJI và Rule 16 (Runtime Test).                                             │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 3. VALIDATION AGENT (Agent Kiểm Duyệt):                                                                │
│   - Duy trì bộ kiểm thử độc lập `test_step7_interactive_app_e2e.py`.                                   │
│   - Chạy 1-Click `run_all_system1_step_tests.bat` đảm bảo 100% ALL PASS (51/51 test cases).            │
│   - Báo cáo định lượng Latency, FPS, Memory usage và cập nhật Sổ Cái Tích Lũy (Rule 15).              │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Hợp Đồng Dữ Liệu Chuẩn Hóa Giữa Các Module (Data Contracts JSON)

Mọi module giao tiếp qua cấu trúc Dict/JSON chuẩn hóa, nghiêm cấm thay đổi cấu trúc gây đứt gãy tương thích:

```json
{
  "slot_id": "slot_004",
  "time_range": {
    "start_sec": 4.0,
    "end_sec": 7.0,
    "display": "00:04 - 00:07"
  },
  "btc_frame": {
    "video_id": "L21_V001",
    "frame_idx": 100,
    "pts_time_sec": 4.0,
    "sharpness": 520.4,
    "objects_formatted": "Người (áo đen) x 1, Xe hơi (màu đen) x 1",
    "ocr_text": "THỜI SỰ 19H",
    "caption_vi": "Không gian bên trong buồng lái xe ô tô ghi nhận người điều khiển phương tiện, xuất hiện Người (áo đen) x 1, Xe hơi (màu đen) x 1.",
    "caption_en": "interior shot inside car cabin showing driver and dashboard on street, featuring person (black clothes) x 1, car (black color) x 1.",
    "border_css": "cyan",
    "is_low_info": false
  },
  "self_frames": [
    {
      "video_id": "L21_V001",
      "frame_idx": 102,
      "pts_time_sec": 4.08,
      "sharpness": 548.2,
      "is_virtual": false,
      "is_deletion_candidate": false,
      "border_css": "normal",
      "delta_meaning": "Bắt đầu cú máy mới trong buồng lái",
      "objects_formatted": "Người (áo đen) x 1, Xe hơi (màu đen) x 1, Điện thoại x 1",
      "caption_vi": "Không gian bên trong buồng lái xe ô tô ghi nhận người điều khiển phương tiện, xuất hiện Người (áo đen) x 1, Xe hơi (màu đen) x 1, Điện thoại x 1.",
      "caption_en": "interior shot inside car cabin showing driver and dashboard on street, featuring person (black clothes) x 1, car (black color) x 1, mobile phone x 1."
    }
  ]
}
```

---

## 4. Lộ Trình Triển Khai & Kế Hoạch Kiểm Thử Từng Bước (Milestone Roadmap)

### Bước 1: Khởi Tạo Service Layer Độc Lập
- Tách các hàm nghiệp vụ (`extract_detected_objects_with_appearance`, `generate_keyframe_bilingual_captions`, `render_side_by_side_comparison`) thành các service riêng biệt trong `services/`.
- **Minh chứng kiểm thử:** Chạy `python -m unittest` hoặc file step test độc lập cho từng service.

### Bước 2: Tách Rời 5 Tab UI Thành Các Component Độc Lập
- Chuyển mã nguồn layout của từng Tab sang `components/tab1_side_by_side.py`, `tab2_storage_hub.py`, v.v.
- `app.py` chỉ còn khoảng ~80 dòng code đóng vai trò lắp ghép Gradio Blocks.

### Bước 3: Tích Hợp Live Dual-Stream (Stream A Local + Stream B Cloud API)
- Kết nối Tab 4 với API LLM / VLM (Gemini / Claude / GPT) theo **Rule 5** để re-rank kết quả tìm kiếm song song với FAISS local.

---

## 5. Nhật Ký Thảo Luận & Quyết Định Kỹ Thuật (Live Discussion Ledger)

| Ngày | Quyết Định Kỹ Thuật & Giải Pháp Thống Nhất | Lý Do & Bối Cảnh Thực Tế | Trạng Thái |
| :--- | :--- | :--- | :--- |
| **24/08/2026** | **Tự Động Mở Trình Duyệt & Giải Phóng Port 7860 Ngầm Không Dừng Chờ Input** | Khi chạy trên Windows qua file `.bat`, các câu lệnh `input()` gây đứng terminal; các socket cũ chưa tắt kịp gây lỗi bận cổng. | **Đã Hoàn Thành (100% Pass)** |
| **24/08/2026** | **Ban Hành Rule 16: Bắt Buộc Test Runtime Thực Tế & Step 7 Test Suite** | Chỉ dùng `py_compile` để lọt lỗi NameError thiếu import `Counter`. Cần test thực thi trực tiếp trên video mẫu và Gradio Blocks. | **Đã Hoàn Thành (100% Pass)** |
| **24/08/2026** | **Tập Trung Hóa Thư Mục `models/` & Phân Tầng YOLOv8n (Local) vs YOLOv8x (Kaggle)** | Cần giải thích rõ ràng tại sao Local CPU dùng bản Nano để tương tác <15ms không giật, còn Kaggle dùng bản X và YOLO-World để bắt văn hóa VN. | **Đã Hoàn Thành (100% Pass)** |
| **24/08/2026** | **Lập Kế Hoạch Module Hóa Kiến Trúc 3 Tầng Cho Studio** | Chuẩn bị sẵn sàng cho các đợt mở rộng tính năng tiếp theo mà không làm gãy mã nguồn hiện hữu. | **Đã Ban Hành Chính Thức** |
