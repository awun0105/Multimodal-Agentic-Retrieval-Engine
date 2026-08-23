# Đề bài và Yêu cầu Kỹ thuật Cuộc thi AIC 2026

## 1. Bài toán (Problem Statement)
- **Mục tiêu:** Truy tìm khoảnh khắc hoặc thông tin trong kho video khổng lồ (vài trăm đến ~1000 giờ) bằng AI.
- **Dữ liệu đầu vào:**
  - Video camera giám sát & vlog cá nhân (Batch 1: 107GB). 
  - Đáng chú ý: BTC cung cấp sẵn Video gốc, **Keyframes** (ảnh cắt sẵn), và **CLIP features** (đặc trưng trích xuất sẵn).
- **3 loại đề chính:**
  1. **KIS (Known-Item Search):** Nhận vào một đoạn mô tả (text) -> Trả về vị trí khoảnh khắc đó (video nào, giây/frame nào).
  2. **Q&A:** Nhận vào câu hỏi về nội dung video -> Trả về câu trả lời ngắn gọn (thường kèm vị trí chứng minh).
  3. **TRAKE:** Nhận vào mô tả một chuỗi N khoảnh khắc/sự kiện -> Trả về N vị trí frame đúng thứ tự thời gian.

## 2. Yêu cầu & Giới hạn Kỹ thuật
- **Giới hạn:** KHÔNG giới hạn mô hình, thuật toán, công cụ. Có thể tự động hoàn toàn hoặc có con người tương tác duyệt kết quả (đề cao UI/UX).
- **Hạ tầng:** BTC KHÔNG cấp máy ảo, GPU hay API. Mọi thứ tự túc.
- **Chiến thuật cho máy yếu (CPU-only):** Tận dụng tối đa tập **CLIP features** của BTC. Việc so khớp vector (tìm kiếm) có thể chạy mượt trên CPU nếu dùng các thư viện như **FAISS**.
- **Tính khả dụng (Availability):** Khuyến khích kiến trúc **Local-first**. Do vòng Chung kết thi Offline chưa rõ có Internet hay không, các tính năng gọi API ngoài (OpenAI, DeepSeek,...) chỉ nên dùng để tăng tốc hoặc là tính năng mở rộng, cần có cơ chế fallback về Local.
- **Tính linh hoạt:** Định dạng file nộp (CSV/JSON) chưa chốt, cần viết module Export tách riêng, dễ dàng sửa đổi.

## 3. Kiến trúc Giải pháp Đề xuất (Tham khảo)
Từ các gợi ý của BTC và các hệ thống cuộc thi chuẩn (LSC/VBS), kiến trúc hệ thống nên được chia thành 3 tầng:

### Tầng 1: Nền móng (Base Pipeline - Bắt buộc)
1. Ingest Data: Keyframes & CLIP features có sẵn.
2. Indexing: Build Vector Index bằng `FAISS` (hoặc tương đương) để tìm kiếm nhanh.
3. Search: Ô tìm kiếm Text -> Vector Similarity Search -> Trả về danh sách Keyframe.
4. UI/UX: Lưới ảnh, cho phép click xem ngữ cảnh video gốc, và module xuất kết quả nộp.

### Tầng 2: Nâng cấp chọn lọc (Advanced Filtering)
- Tích hợp Database để quản lý và lọc Metadata (Thời gian, video ID) kết hợp Vector Search (VD: `Elasticsearch`, `Milvus`, `Qdrant`,...).
- Tích hợp Object Detection & OCR lên các keyframe để lọc từ khóa (VD: có biển số xe, có chữ X).
- Module riêng cho TRAKE: Xử lý Tách câu mô tả -> Tìm từng sự kiện (KIS) -> Nối và lọc chuỗi theo ràng buộc thời gian cùng một video.

### Tầng 3: Tầng AI Agent & RAG (Khuyến khích cao)
- **Agent Q&A (Khung STAR):** Dùng LLM đóng vai trò điều phối (Orchestrator) gọi tới các công cụ xử lý không gian (phóng to, OCR, Object Detection) và thời gian (chọn keyframe, cắt đoạn video) để suy luận trả lời.
- **Conversational Search (RAG):** Hệ thống có khả năng tương tác với người dùng qua Chat để chuẩn hóa câu hỏi, thêm các bộ lọc phụ (metadata), re-rank lại kết quả trước khi đưa ra danh sách đáp án cuối cùng.
- **Reference:** Tham khảo kiến trúc của **MemoriEase 2.0 / 3.0** (hệ thống được BTC đặc biệt nhắc tới).
