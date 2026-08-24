# TRÌNH ĐIỀU KHIỂN & BENCHMARK STUDIO TRỰC QUAN (AIC 2026)

Hệ thống Interactive Studio được thiết kế theo tiêu chuẩn tương tác quốc tế VBS / LSC phục vụ cuộc thi AI Challenge 2026, cho phép đối chiếu trực quan từng giây giữa dữ liệu Ban Tổ Chức (BTC) và Pipeline Tự Xử Lý (System 1 & System 2).

---

## 1. Khởi Động Nhanh 1-Click

Nhấp đúp chuột vào tệp:
[start_interactive_test_app.bat](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/start_interactive_test_app.bat)

*Hệ thống sẽ tự động dọn sạch cổng 7860, khởi động máy chủ và tự động mở trình duyệt tại `http://127.0.0.1:7860`.*

---

## 2. Kiến Trúc 3 Tầng Phân Rã Độc Lập

Toàn bộ ứng dụng đã được tái cấu trúc thành 3 tầng chuẩn mực:

```
interactive-test-app/
├── app.py                     # Root Assembler (<170 dòng) kết nối UI, quản lý Port & re-export 100%
├── run_studio_tests.bat       # Script 1-Click chạy toàn bộ kiểm tra cấu trúc & runtime Studio
├── test_studio_structure.py   # Test suite kiểm tra tính toàn vẹn cấu trúc 3 tầng & contracts
├── ARCHITECTURE_AND_TESTING_GUIDE.md # Tài liệu kiến trúc và hướng dẫn kiểm thử chi tiết
├── services/                  # TẦNG 2: NGHIỆP VỤ & XỬ LÝ DỮ LIỆU THUẦN TÚY (Data & Business Logic)
│   ├── config.py              # Single Source of Truth cho đường dẫn, hằng số, target videos
│   ├── model_service.py       # Quản lý YOLO, CLIP, FAISS, In-Memory Zip Cache reader
│   ├── appearance_service.py  # Thuật toán màu HSV, phrasing tự nhiên, YOLO detector, phân tích phổ ảnh
│   ├── caption_service.py     # Sinh cặp miêu tả Decoupled Dual-Channel tự thân độc lập
│   ├── timeline_service.py    # Cắt keyframe trần 2.5s, cache CSV, đồng bộ Side-by-Side timeline
│   ├── persistence_service.py # Tổng hợp bảng thống kê WebP tiết kiệm đĩa, xuất zip dataset
│   └── search_service.py      # Bảng thanh tra đa phương thức Steps 1-6 và xuất báo cáo CSV/JSON
├── templates/                 # TẦNG 3: GIAO DIỆN TRÌNH BÀY & CSS (Presentation & CSS Design Tokens)
│   ├── theme_tokens.py        # Toàn bộ CSS dark theme tokens (Nord & Dracula Palette)
│   └── card_templates.py      # Renderers HTML thẻ bài timeline, mốc thời gian trung tâm, holding row
├── components/                # TẦNG 1: THÀNH PHẦN GIAO DIỆN TỪNG TAB (UI Tabs)
│   ├── tab1_side_by_side.py   # Tab 1: So sánh Side-by-Side BTC vs System 1
│   ├── tab2_storage_hub.py    # Tab 2: Quản lý lưu trữ & Persistence summary
│   ├── tab3_multimodal_matrix.py # Tab 3: Bảng so sánh đa phương thức Steps 1-6
│   ├── tab4_hybrid_search.py  # Tab 4: Tìm kiếm trực quan & KIS search
│   └── tab5_parameter_tuning.py # Tab 5: Studio tùy chỉnh tham số đầu vào
└── plans/
    └── STUDIO_MODULAR_ARCHITECTURE_AND_EXPANSION_PLAN.md # Kế hoạch kiến trúc & Governance Matrix
```

---

## 3. Bản Đồ 5 Phân Hệ Trực Quan

1. **TAB 1: SO SÁNH TRỰC QUAN SIDE-BY-SIDE (BTC vs. SYSTEM 1 TỰ XỬ LÝ)**
   - Đối chiếu theo từng Time Slot 3 giây; đồng bộ nhất quán phát hiện vật thể giữa 2 bên.
   - Thẻ Song Ngữ: [BẢN MIÊU TẢ TIẾNG VIỆT] (bối cảnh khách quan + phụ lục thực thể) + [DỊCH & LÀM GIÀU EN CHO SIGLIP].
   - Trích Xuất Ngoại Hình: Bắt màu áo (áo đen, áo trắng, áo xanh...) và màu xe (xe đen, xe đỏ...).
   - Frame Cắt Nghĩa (Virtual Frame viền tím): Dùng chung ảnh với Anchor -> Tiết kiệm 100% đĩa.
2. **TAB 2: QUẢN LÝ LƯU TRỮ & DỮ LIỆU ĐÃ TRÍCH XUẤT (PERSISTENCE & STORAGE HUB)**
   - Thống kê toàn bộ video, số shot, độ nét trung bình, dung lượng WebP, xuất CSV & JSON nộp bài.
3. **TAB 3: BẢNG SO SÁNH ĐA PHƯƠNG THỨC & KẾT QUẢ XỬ LÝ CHI TIẾT (MULTIMODAL MATRIX)**
   - Báo cáo chi tiết OCR 2-Tier, ma trận so sánh SigLIP 1152d vs ViSigLIP 768d, ASR Video QA.
4. **TAB 4: TÌM KIẾM TRỰC QUAN KIS & VIDEO QA (SYSTEM 2 DUAL-STREAM HYBRID RETRIEVAL)**
   - Tìm kiếm lai đa tầng: FAISS Dense + FTS5 BM25 + ASR QA với cơ chế Toggle On/Off động.
5. **TAB 5: STUDIO TÙY CHỈNH THAM SỐ ĐẦU VÀO (SYSTEM 1 PARAMETER TUNING)**
   - Tinh chỉnh trực quan ngưỡng cắt cảnh, bộ lọc độ nét, kích thước thumbnail.

---

## 4. Hướng Dẫn Sử Dụng Bộ Tester Đảm Bảo Cấu Trúc

1. **Chạy kiểm tra toàn vẹn cấu trúc 3 tầng:**
   ```powershell
   python interactive-test-app/test_studio_structure.py
   ```
2. **Chạy kiểm tra runtime E2E cả 5 Tabs:**
   ```powershell
   python system1-kaggle-pipeline/scripts/steps/test_step7_interactive_app_e2e.py
   ```
3. **Chạy 1-Click toàn bộ kiểm thử Studio:**
   ```powershell
   cmd.exe /c interactive-test-app/run_studio_tests.bat
   ```

---

## 5. Tài Liệu Tham Khảo Chi Tiết

- [Kiến Trúc 3 Tầng & Hướng Dẫn Vận Hành, Kiểm Thử](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/interactive-test-app/ARCHITECTURE_AND_TESTING_GUIDE.md)
- [Hướng Dẫn Toàn Diện Vận Hành & Xử Lý Sự Cố Studio](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/interactive-test-app/INTERACTIVE_STUDIO_USER_GUIDE_AND_TROUBLESHOOTING.md)
- [Sổ Tay Phòng Ngừa Lỗi & Dữ Liệu Biên (Edge Cases)](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/interactive-test-app/ERROR_PREVENTION_AND_EDGE_CASES_README.md)
- [Sổ Cái Tích Lũy Ý Tưởng Người Dùng](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/.agents/notes/user_ideas_and_solutions_ledger.md)
