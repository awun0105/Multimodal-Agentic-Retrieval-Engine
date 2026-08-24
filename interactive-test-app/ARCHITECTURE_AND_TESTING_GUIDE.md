# Kiến Trúc 3 Tầng & Hướng Dẫn Vận Hành, Kiểm Thử Studio (AIC 2026)

Tài liệu này cung cấp bức tranh toàn cảnh về kiến trúc hệ thống, luồng dữ liệu, quy trình mở rộng và bộ công cụ kiểm thử (Testers) dành cho các Kỹ sư AI và AI Agent kế nhiệm.

---

## 1. Bức Tranh Tổng Thể Kiến Trúc 3 Tầng (3-Tier Architecture Blueprint)

Thư mục `interactive-test-app/` được tổ chức theo mô hình phân tách trách nhiệm nghiêm ngặt:

```
interactive-test-app/
├── app.py                     # Root Assembler (<170 dòng) kết nối UI, quản lý Port mạng & re-export 100%
├── run_studio_tests.bat       # Script 1-Click chạy toàn bộ kiểm tra cấu trúc & runtime Studio
├── test_studio_structure.py   # Test suite kiểm tra tính toàn vẹn cấu trúc 3 tầng & contracts
├── ARCHITECTURE_AND_TESTING_GUIDE.md # Tài liệu kiến trúc và hướng dẫn kiểm thử (File này)
├── services/                  # TẦNG 2: NGHIỆP VỤ & XỬ LÝ DỮ LIỆU THUẦN TÚY (Data & Business Logic)
│   ├── __init__.py            # Re-export clean service APIs
│   ├── config.py              # Single Source of Truth (SSOT) cho đường dẫn, hằng số, target videos
│   ├── model_service.py       # Quản lý YOLO, CLIP, FAISS, In-Memory Zip Cache reader
│   ├── appearance_service.py  # Thuật toán màu HSV, phrasing tự nhiên, YOLO detector, phân tích phổ ảnh
│   ├── caption_service.py     # Sinh cặp miêu tả Decoupled Dual-Channel tự thân độc lập
│   ├── timeline_service.py    # Cắt keyframe trần 2.5s, cache CSV, đồng bộ Side-by-Side timeline
│   ├── persistence_service.py # Tổng hợp bảng thống kê WebP tiết kiệm đĩa, xuất zip dataset
│   └── search_service.py      # Bảng thanh tra đa phương thức Steps 1-6 và xuất báo cáo CSV/JSON
├── templates/                 # TẦNG 3: GIAO DIỆN TRÌNH BÀY & CSS (Presentation & CSS Design Tokens)
│   ├── __init__.py            # Re-export templates & CSS
│   ├── theme_tokens.py        # Toàn bộ CSS dark theme tokens (Nord & Dracula Palette)
│   └── card_templates.py      # Renderers HTML thẻ bài timeline, mốc thời gian trung tâm, holding row
├── components/                # TẦNG 1: THÀNH PHẦN GIAO DIỆN TỪNG TAB (UI Tabs)
│   ├── __init__.py            # Re-export create_tab_*
│   ├── tab1_side_by_side.py   # Tab 1: So sánh Side-by-Side BTC vs System 1
│   ├── tab2_storage_hub.py    # Tab 2: Quản lý lưu trữ & Persistence summary
│   ├── tab3_multimodal_matrix.py # Tab 3: Bảng so sánh đa phương thức Steps 1-6
│   ├── tab4_hybrid_search.py  # Tab 4: Tìm kiếm trực quan & KIS search
│   └── tab5_parameter_tuning.py # Tab 5: Studio tùy chỉnh tham số đầu vào
└── plans/
    └── STUDIO_MODULAR_ARCHITECTURE_AND_EXPANSION_PLAN.md # Kế hoạch kiến trúc & Governance Matrix
```

---

## 2. Sơ Đồ Luồng Dữ Liệu (Data Flow)

```
[Video Input / Zip Blob / Query]
               │
               ▼
   ┌────────────────────────────────────────┐
   │        TẦNG 2: SERVICES                │
   │  - Trích xuất keyframe trần <= 2.5s    │
   │  - Bóc tách màu sắc HSV & Phrasing     │
   │  - Decoupled Bilingual Captioning      │
   │  - Đồng bộ dòng thời gian & khử trùng  │
   └───────────────────┬────────────────────┘
                       │ (Dữ liệu có cấu trúc Dict / DataFrame)
                       ▼
   ┌────────────────────────────────────────┐
   │        TẦNG 3: TEMPLATES               │
   │  - Render HTML Card frames             │
   │  - Tạo Badge trạng thái (Cyan, Tím, Đỏ)│
   │  - Áp dụng CSS Nord/Dracula            │
   └───────────────────┬────────────────────┘
                       │ (Chuỗi HTML hoàn chỉnh & Theme CSS)
                       ▼
   ┌────────────────────────────────────────┐
   │        TẦNG 1: COMPONENTS              │
   │  - Tab 1: Side-by-Side Timeline        │
   │  - Tab 2: Persistence Storage Hub      │
   │  - Tab 3: Multimodal Inspection Matrix │
   │  - Tab 4: Hybrid KIS Search            │
   │  - Tab 5: Parameter Tuning Studio      │
   └───────────────────┬────────────────────┘
                       │ (Khối Gradio TabItems & Event Listeners)
                       ▼
   ┌────────────────────────────────────────┐
   │        ROOT ASSEMBLER: app.py          │
   │  - Lắp ráp Blocks: build_app()         │
   │  - Giải phóng Port mạng tự động        │
   │  - Khởi chạy Web Server: app.launch()  │
   └────────────────────────────────────────┘
```

---

## 3. Hướng Dẫn Phát Triển Cho AI Agent Kế Nhiệm

### 3.1. Thêm Một Tab Giao Diện Mới
1. Tạo tệp `components/tabX_ten_tinh_nang.py`.
2. Định nghĩa hàm `create_tab_ten_tinh_nang()` trả về một dictionary chứa các widget tương tác.
3. Đăng ký hàm vào `components/__init__.py`.
4. Mở `app.py`, import hàm và gọi `tabX_widgets = create_tab_ten_tinh_nang()` bên trong khối `with gr.Tabs():` của `build_app()`.

### 3.2. Thêm Logic / Thuật Toán Nghiệp Vụ Mới
1. Thêm hàm nghiệp vụ vào đúng file service tương ứng trong `services/` (hoặc tạo service mới nếu là mảng hoàn toàn riêng biệt).
2. Viết docstring giải thích rõ đầu vào (Inputs), đầu ra (Outputs), và các ngoại lệ có thể xảy ra.
3. Re-export hàm đó trong `services/__init__.py` và `app.py`.

### 3.3. Quy Chuẩn Không Xâm Phạm (Strict Constraints)
- **Tuyệt đối KHÔNG** chứa mã HTML dài hoặc logic nặng trực tiếp trong `app.py`.
- **Tuyệt đối KHÔNG** sử dụng emoji/icon trong toàn bộ mã nguồn, chú thích, tài liệu hay log.
- **Bắt buộc** duy trì 100% Backward Compatibility cho các hàm re-export trong `app.py`.

---

## 4. Hướng Dẫn Sử Dụng Bộ Tester & Kiểm Thử Tự Động

Chúng tôi cung cấp 3 cấp độ kiểm định từ nhanh đến toàn diện:

### Cấp độ 1: Kiểm Tra Toàn Vẹn Cấu Trúc Studio (Structural Integrity Test)
Kiểm tra cấu trúc thư mục, kiểm tra import độc lập không lỗi, kiểm tra khởi tạo từng Tab trong Gradio Blocks:
```powershell
python interactive-test-app/test_studio_structure.py
```

### Cấp độ 2: Kiểm Tra Runtime E2E Studio (Step 7 Runtime Test)
Kiểm tra bóc tách màu HSV trên ảnh thực tế, kiểm tra Natural Phrasing, Caption song ngữ Decoupled, render Side-by-Side trên video thật `L21_V001` và các event handlers cả 5 Tabs:
```powershell
python system1-kaggle-pipeline/scripts/steps/test_step7_interactive_app_e2e.py
```

### Cấp độ 3: Chạy Kiểm Thử 1-Click Toàn Hệ Thống (Full Batch Suite)
Chạy toàn bộ 7/7 Step Suites của cuộc thi AIC:
```powershell
cmd.exe /c run_all_system1_step_tests.bat
```
Hoặc chạy riêng cho Studio:
```powershell
cmd.exe /c interactive-test-app/run_studio_tests.bat
```
