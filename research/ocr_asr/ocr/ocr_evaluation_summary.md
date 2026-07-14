# Bảng Nhận Xét & So Sánh 5 Pipeline OCR trên GPU

Dưới đây là bảng đánh giá chi tiết về tốc độ (Latency), độ chính xác nhận diện tiếng Việt và khả năng ứng dụng thực tế của từng mô hình sau khi chạy thực nghiệm trên GPU **NVIDIA GeForce RTX 4060 Laptop**.

---

## 1. Bảng So Sánh Tổng Quan

| Pipeline | Thời gian trung bình / ảnh (s) | Chất lượng Tiếng Việt | Ưu điểm | Nhược điểm | Đánh giá chung |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **EasyOCR** | 0.0605s | **Xuất sắc (9.5/10)** | - Nhận diện dấu Tiếng Việt rất chuẩn.<br>- Xử lý nhanh nhờ tối ưu hóa trên GPU. | - Đôi lúc nhận diện sai các ký tự rất nhỏ. | **Khuyên dùng** cho các ứng dụng thực tế cần độ chính xác cao về Tiếng Việt. |
| **PaddleOCR Only** | **0.0386s** | Khá (7.5/10) | - Tốc độ nhanh nhất.<br>- Nhận diện biên chữ (detector) cực kỳ chính xác. | - Thường xuyên bỏ sót dấu hoặc viết sai dấu Tiếng Việt. | **Phù hợp nhất** khi cần xử lý thời gian thực (Real-time) và không quá khắt khe về dấu câu. |
| **PaddleOCR + VietOCR** | 0.1222s | Tệ (2.0/10) | - Tách hộp chữ tốt bằng Paddle. | - Bị lỗi phân bổ trọng số checkpoint địa phương (`vgg_seq2seq`) dẫn đến sinh chuỗi lặp vô nghĩa (`001000000100`). | **Cần thay thế/huấn luyện lại** checkpoint VietOCR để hoạt động bình thường. |
| **PaddleOCR + TrOCR** | 0.1781s | Rất tệ (1.5/10) | - Nhận diện chữ tiếng Anh tốt. | - Model gốc `trocr-base-printed` chỉ hỗ trợ Tiếng Anh nên không thể nhận diện Tiếng Việt. | **Không khuyên dùng** cho dữ liệu tiếng Việt trừ phi fine-tune lại TrOCR. |
| **Florence-2** | 2.5993s | Rất tệ (1.0/10) | - Có thể cấu trúc hóa dữ liệu đầu ra tốt (dạng JSON/Bounding Box). | - Thời gian xử lý quá lâu.<br>- Checkpoint gốc tiếng Anh bị ảo giác (hallucination) nghiêm trọng khi gặp Tiếng Việt. | **Không phù hợp** cho bài toán OCR Tiếng Việt thông thường. |

---

## 2. Nhận Xét Chi Tiết & Khuyến Nghị

### 🥇 Top 1: EasyOCR (Độ chính xác cao nhất)
- **Độ chính xác Tiếng Việt:** Vượt trội so với các pipeline còn lại. Nhờ model nhận diện được tối ưu hóa cho tiếng Việt, EasyOCR khôi phục hầu như hoàn hảo các từ tiếng Việt phức tạp như `HẠ TẤNG KỸ THUẬT SỜ XẬY DỰNG TPHCM`.
- **Tốc độ:** Với trung bình **0.0605 giây/ảnh**, EasyOCR cực kỳ tối ưu khi chạy trên GPU.

### ⚡ Top 2: PaddleOCR Only (Tốc độ nhanh nhất)
- **Tốc độ:** Đạt hiệu năng ấn tượng **0.0386 giây/ảnh**, nhanh gấp 1.5 lần so với EasyOCR.
- **Độ chính xác Tiếng Việt:** Detector PP-OCRv5 tìm vùng chữ rất nhạy, nhưng mô hình recognition mặc định bị thiếu hụt bộ từ điển tiếng Việt chuẩn nên hay làm mất dấu (ví dụ: `Ông Đ TN LONG PH GIM ĐC...`).

### ⚠️ Các Pipeline khác
- **PaddleOCR + VietOCR:** Gặp lỗi tương thích với phiên bản Pillow 10+ (đã được sửa bằng patch `Image.ANTIALIAS`) nhưng chất lượng nhận diện của checkpoint `vgg_seq2seq` đi kèm bị suy hao nghiêm trọng (chỉ ra chuỗi số vô nghĩa).
- **TrOCR & Florence-2:** Hoàn toàn không phù hợp cho tiếng Việt nếu không được tinh chỉnh (fine-tune) lại trên tập dữ liệu tiếng Việt. Florence-2 cũng có độ trễ rất lớn (2.6s) không phù hợp cho các luồng xử lý tốc độ cao.
