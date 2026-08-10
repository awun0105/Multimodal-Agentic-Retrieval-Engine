# Bản đồ Nghiên cứu & Trạng thái Phân hệ Embedding (Embedding Plan & Status)

Tài liệu này đóng vai trò là "la bàn" chỉ hướng cho mảng nghiên cứu **Multimodal Embedding** – một trong ba trụ cột AI cốt lõi của dự án *Multimodal Agentic Retrieval Engine* (AIC 2026).

---

## I. Tầm nhìn và Vị trí trong Hệ thống (Context & Architecture)

Trong kiến trúc 3 tầng của hệ thống (Base Pipeline -> Advanced Filtering -> AI Agent), phân hệ Embedding đóng vai trò là "viên gạch nền móng" của **Tầng 1 (Base Pipeline)**.

**Mục tiêu Lõi:** Tìm ra một mô hình biến đổi Dữ liệu Đa phương thức (Ảnh và Văn bản) thành các Vector (Chuỗi số thực) sao cho:
1. Đảm bảo tốc độ trích xuất cực nhanh (giải bài toán I/O và VRAM trên Kaggle/Colab).
2. Tối ưu tìm kiếm bằng thuật toán **FAISS**.
3. Là công cụ mũi nhọn để giải quyết đề thi **KIS (Known-Item Search)**: Tìm một khoảnh khắc cụ thể thông qua truy vấn văn bản của người dùng.
4. Đảm bảo tính khả dụng Local-first (chạy tốt bằng CPU/GPU máy tính cá nhân khi thi Offline).

Kết quả cuối cùng của phân hệ này sẽ được trừu tượng hóa (encapsulate) thành một hàm duy nhất `get_vector(input_data)` để các module khác (như FAISS Indexer) có thể gọi và tái sử dụng dễ dàng.

---

## II. Trạng thái Hiện tại (Current Status)

Chúng ta hiện đang ở giai đoạn tuyển chọn mô hình khắt khe nhất. Quá trình đánh giá được chia làm hai tiêu chí chính: **Tốc độ (Speed/Latency/VRAM)** và **Độ chính xác (Accuracy)**.

### ✅ Đã Hoàn thành (Phase 1: Speed & VRAM Benchmark)
- **Thiết lập Môi trường:** Đã xây dựng hoàn chỉnh kịch bản xử lý I/O độc quyền để lách luật 20GB ổ đĩa của Kaggle (chiến thuật *Virtual Cache .blob* & *Colab Data Prep*).
- **Thực thi Đo đạc:** Đã cấu hình và chạy Grand Benchmark trên **24 mô hình SOTA** (State-of-the-Art) trải dài từ kiến trúc LLM-based, OpenCLIP, SentenceTransformers đến SigLIP.
- **Tiêu chí vạch ra:** Đã chọn lọc được Top các mô hình có độ trễ cực thấp (Image Batch & Text Batch < 50ms) và VRAM tối thiểu để phù hợp với tài nguyên bị giới hạn.

---

## III. Kế hoạch Các Bước Tiếp Theo (The Next Steps)

Dưới đây là kế hoạch chi tiết cho các chặng đường sắp tới để hoàn thiện toàn bộ luồng Embedding:

### ⏳ Phase 2: Đánh giá Độ chính xác (Accuracy Benchmark) - Sắp diễn ra
Tốc độ nhanh là chưa đủ nếu mô hình "hiểu" sai ngữ nghĩa hình ảnh. Ở giai đoạn này, chúng ta sẽ:
1. **Lọc Ứng viên:** Lấy ra Top 3 - 5 mô hình xuất sắc nhất từ kết quả báo cáo của Phase 1 (ưu tiên các phiên bản hỗ trợ Tiếng Việt tốt như Jina-CLIP hoặc đa ngôn ngữ như SigLIP-i18n, AltCLIP).
2. **Bộ dữ liệu (Dataset):** Sử dụng một tập dữ liệu nhỏ có dán nhãn chuẩn mực (VD: Một phần của bộ COCO, Flickr30k hoặc tự sample + gán nhãn thủ công từ 1-2 video AIC 2025).
3. **Tiêu chí Đánh giá:** 
   - Điểm Cosine Similarity trung bình giữa Ảnh và Câu mô tả khớp (Positive Pairs).
   - Chỉ số **Zero-shot Recall@1, Recall@5, Recall@10** trên tập truy vấn văn bản.

### ⏳ Phase 3: Hiện thực hóa Hàm Lõi (Core Function Integration)
Sau khi chốt hạ được 1 mô hình duy nhất chiến thắng cả về tốc độ lẫn độ chính xác:
1. **Đóng gói mã nguồn:** Xây dựng file mã nguồn hoàn chỉnh chứa hàm `get_vector(input_data)` như đã hứa trong biên bản `Ban_chia_viec_nghien_cuu_multimodal.md`.
2. **Xử lý lô (Batching):** Thiết kế bộ xử lý hàng loạt (Batch Vectorization) với thư viện DataLoader để đẩy mạnh tốc độ trích xuất toàn bộ Keyframes.
3. **Chuyển giao (Hand-off):** Tạo Pull Request (PR) lên nhánh `research-branch` (hoặc nhánh `system1-notebook01`) kèm theo module ghi tệp dữ liệu Vector định dạng `.faiss`.

### ⏳ Phase 4: Tối ưu cho Môi trường Offline (CPU & Local-first Optimization)
BTC yêu cầu tính linh hoạt cao và ưu tiên máy yếu. Do đó, mô hình chiến thắng sẽ cần được "độ" lại:
1. **Lượng tử hóa (Quantization):** Nghiên cứu chuyển đổi trọng số mô hình sang định dạng ONNX hoặc sử dụng thư viện OpenVINO để ép mô hình chạy mượt trên CPU truyền thống.
2. **Dự phòng (Fallback):** Đảm bảo hệ thống có cơ chế chuyển đổi mềm mại giữa việc gọi qua API (nếu thi Online có Internet) và xử lý cục bộ hoàn toàn.

---

## IV. Cột mốc Nghiệm thu (Milestones)

- [x] Lên danh sách 24 mô hình ứng viên.
- [x] Vượt qua bài kiểm thử Tốc độ và Dung lượng VRAM (Phase 1).
- [ ] Báo cáo kết quả Độ chính xác và chọn ra "Quán quân" (Phase 2).
- [ ] Mã nguồn Python `get_vector` chạy ổn định, sạch sẽ, không rò rỉ RAM (Phase 3).
- [ ] Báo cáo tổng kết (`report.md`) nghiệm thu mảng Embedding.
