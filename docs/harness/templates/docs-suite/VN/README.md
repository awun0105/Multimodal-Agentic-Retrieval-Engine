<!-- 
BẢN MẪU TÀI LIỆU: Danh mục Tiếng Việt
====================================
Trọng tâm: Lộ trình chi tiết và bản đồ từng tệp cho bộ tài liệu tiếng Việt.

I. GIAO THỨC THỰC THI CHO AGENT (DÀNH CHO AI):
1. THU THẬP NGỮ CẢNH: Quét thư mục `docs/VN` để tìm tất cả các tệp tài liệu hiện có.
2. ĐIỀN DỮ LIỆU: Giải quyết [Tên Dự án].
3. TỐI ƯU HÓA: Loại bỏ các liên kết đến các tệp không tồn tại trong thư mục tài liệu của dự án.
4. LÀM SẠCH: Xóa bỏ tất cả ghi chú in nghiêng và khối hướng dẫn này.

II. HƯỚNG DẪN TÙY BIẾN CHO NGƯỜI DÙNG:
1. ĐIỀU HƯỚNG: Đảm bảo danh sách "Đọc theo thứ tự sau" phản ánh đúng độ phức tạp và cấu trúc thực tế của dự án bạn.
2. BẢN ĐỒ TỆP: Cập nhật bảng để bao gồm bất kỳ tệp tài liệu tùy chỉnh nào bạn đã thêm vào (ví dụ: `security-audit.md`).
3. HOÀN THIỆN: Xác minh tất cả các liên kết nội bộ hoạt động chính xác. Xóa văn bản hướng dẫn (chữ *in nghiêng*) trước khi xuất bản.
-->

# Tài liệu Tiếng Việt

Đây là bộ tài liệu chính thức và toàn diện cho dự án **[Tên Dự án]**.

Đọc theo thứ tự sau nếu bạn là người mới tiếp cận dự án:

1. [Tổng quan](overview.md)
2. [Kiến trúc hệ thống](architecture.md)
3. [Luồng dữ liệu](data-flow.md)
4. [Cấu hình](configuration.md)
5. [Phát triển cục bộ](local-development.md)
6. [Thiết lập Production](deployment/setup.md)
7. [Tham chiếu API](api.md)
8. [Script bảo trì](scripts.md)
9. [Đánh giá hệ thống](evaluation.md)
10. [Vận hành](operations.md)
11. [Sao lưu và phục hồi](deployment/backup-restore.md)

## Danh sách tệp tin

| Tệp tin | Mục đích |
|---|---|
| [overview.md](overview.md) | Giải thích dịch vụ làm gì, vai trò trong hệ thống và phạm vi dự án. |
| [architecture.md](architecture.md) | Giải thích các thành phần, trách nhiệm, lựa chọn lưu trữ và ý tưởng thực thi. |
| [data-flow.md](data-flow.md) | Hiển thị luồng dữ liệu cho tìm kiếm, lập chỉ mục, trạng thái và lưu trữ. |
| [configuration.md](configuration.md) | Giải thích về `.env`, `.env.production`, các thiết lập và quản lý thông tin xác thực. |
| [local-development.md](local-development.md) | Hướng dẫn từng bước thiết lập tại máy cục bộ để lập trình và gỡ lỗi. |
| [deployment/setup.md](deployment/setup.md) | Hướng dẫn từng bước thiết lập môi trường production (Docker/VPS). |
| [api.md](api.md) | Các endpoint API, ví dụ yêu cầu/phản hồi và cơ chế xác thực. |
| [scripts.md](scripts.md) | Các script bảo trì cho di chuyển dữ liệu, đánh giá và tự động hóa. |
| [evaluation.md](evaluation.md) | Các tiêu chí chất lượng truy xuất, công cụ benchmark và mẫu kết quả. |
| [operations.md](operations.md) | Kiểm tra sức khỏe, số liệu, logs, trạng thái job và các kiểm tra vận hành thông thường. |
| [deployment/backup-restore.md](deployment/backup-restore.md) | Quy trình bảo tồn trạng thái và xác minh phục hồi sau sự cố. |

---

<div align="center">

[Quay lại Bản đồ Tài liệu](../README.md)

</div>
