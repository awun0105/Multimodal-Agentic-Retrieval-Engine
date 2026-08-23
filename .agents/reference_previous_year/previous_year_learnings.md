# Bài Học Kinh Nghiệm & Mã Nguồn Tái Sử Dụng Từ AIC 2025 (Danh-AIC)

Tài liệu này tổng hợp lại kiến trúc, bài học kinh nghiệm và danh sách các module mã nguồn đã được trích xuất từ dự án **Image-Retrieval-System-for-AIC2025** (`C:\Nhat_Code\aio\project\AIC\Danh-AIC\Image-Retrieval-System-for-AIC2025`) để phục vụ dự án mới **Multimodal Agentic Retrieval Engine** (AIC 2026 - Chủ đề Thể thao / Sports).

---

## I. Vị Trí Lưu Trữ Mã Nguồn Cũ (Legacy Code)

Toàn bộ các service và script quan trọng của năm ngoái đã được copy vào dự án tại:
- **Thư mục chứa code cũ:** `scripts/legacy_2025/`
  - [`scripts/legacy_2025/query_rewrite_service.py`](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine-master/Multimodal-Agentic-Retrieval-Engine-master/scripts/legacy_2025/query_rewrite_service.py): Service LLM viết lại câu truy vấn chứa tên riêng thành mô tả ngoại hình trực quan.
  - [`scripts/legacy_2025/video_ranking_service.py`](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine-master/Multimodal-Agentic-Retrieval-Engine-master/scripts/legacy_2025/video_ranking_service.py): Algorithmic DANTE / Dynamic Programming giải bài toán chuỗi thời gian TRAKE.
  - [`scripts/legacy_2025/model_service.py`](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine-master/Multimodal-Agentic-Retrieval-Engine-master/scripts/legacy_2025/model_service.py): Wrapper class cho model BEiT-3 & chuẩn hóa L2 norm vector.
  - [`scripts/legacy_2025/keyframe_migration.py`](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine-master/Multimodal-Agentic-Retrieval-Engine-master/scripts/legacy_2025/keyframe_migration.py): Script chuyển đổi ánh xạ `id2index.json` và `video_index_ranges.json`.
  - [`scripts/legacy_2025/ocr_service.py`](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine-master/Multimodal-Agentic-Retrieval-Engine-master/scripts/legacy_2025/ocr_service.py) & [`asr_service.py`](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine-master/Multimodal-Agentic-Retrieval-Engine-master/scripts/legacy_2025/asr_service.py): Các service xử lý OCR và ASR cơ bản.

---

## II. Đánh Giá & Bài Học Kinh Nghiệm Tái Sử Dụng

### 1. Mảng Embedding (Vector hóa Ảnh & Text)
- **Năm ngoái:** Sử dụng **BEiT-3** (`core/beit3_processor.py`).
- **Bài học:** 
  - Vector trước khi đẩy vào FAISS bắt buộc phải thực hiện **L2 Normalization**:
    `features = features / features.norm(p=2, dim=-1, keepdim=True)`
  - Thiết kế class wrapper dạng Singleton / Factory để tránh load lại model nhiều lần gây tốn VRAM/RAM.
- **Áp dụng 2026:** Giữ nguyên cấu trúc Wrapper của `model_service.py`, thay core model bằng **SigLIP** (`google/siglip-base-patch16-224`) hoặc **BGE-Visual** để nhẹ hơn và tối ưu CPU hơn.

### 2. Mảng Query Rewrite bằng LLM (Đặc biệt hiệu quả cho Thể thao / Sports)
- **Năm ngoái:** Viết service `QueryRewriteService` dùng GPT-4o-mini / Gemini 1.5 Flash chuyển tên riêng thành câu mô tả màu sắc, hình dáng.
- **Áp dụng 2026 (Chủ đề Sports):** 
  - Trong video thể thao có rất nhiều tên vận động viên (*Messi, Ronaldo, Ánh Viên*), tên đội bóng (*Real Madrid, Chicago Bulls*), hoặc tên môn thể thao đặc thù.
  - Tận dụng nguyên vẹn `query_rewrite_service.py`, chỉ cần điều chỉnh **System Prompt** hướng về chủ đề Thể thao (mô tả màu áo đấu, logo, hành động thể thao như sút bóng, nhảy rào, giao bóng).

### 3. Bài toán TRAKE (Temporal Event Search)
- **Năm ngoái:** Thuật toán **DANTE (Dynamic Programming)** tìm chuỗi sự kiện $f_1 < f_2 < ... < f_N$ theo thứ tự thời gian trong cùng một video.
- **Áp dụng 2026:**
  - Thể thao có tính chất chuỗi hành động rõ ràng (*"VĐV lấy đà -> Nhảy qua rào -> Tiếp đất"*).
  - Tái sử dụng hàm DP trong `video_ranking_service.py` đưa vào tầng **Advanced Filtering** của hệ thống mới.

---

## III. Hướng Dẫn Tích Hợp Vào Dự Án Mới

1. **Cho Người phụ trách Embedding (Mảng 1):** Tham khảo file `scripts/legacy_2025/model_service.py` để lấy cách chuẩn hóa L2 vector và cấu trúc hàm `embedding(text)` / `embedding_image(img)`.
2. **Cho Người phụ trách RAG / Agent Query (Mảng 3):** Sử dụng `scripts/legacy_2025/query_rewrite_service.py` làm module tiền xử lý câu truy vấn trước khi đẩy vào FAISS search.
3. **Cho Người phụ trách Indexing & Data:** Sử dụng `scripts/legacy_2025/keyframe_migration.py` để tham khảo cách tạo mapping `id2index.json` và `video_index_ranges.json` cho FAISS và SQLite.
