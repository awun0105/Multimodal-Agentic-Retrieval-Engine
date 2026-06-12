<!-- 
BẢN MẪU TÀI LIỆU: Vận hành
=========================
Trọng tâm: Giám sát sức khỏe, số liệu hiệu năng, chiến lược ghi nhật ký và quản lý tác vụ.

I. GIAO THỨC THỰC THI CHO AGENT (DÀNH CHO AI):
1. THU THẬP NGỮ CẢNH: Xác định các endpoint vận hành (/health, /metrics), định dạng log (JSON/Văn bản) và các hệ thống xử lý tác vụ nền.
2. ĐIỀN DỮ LIỆU: Thay thế tất cả các nhãn trong dấu ngoặc vuông `[ ]` bằng các cổng, đường dẫn và nhãn số liệu thực tế của dự án.
3. TỐI ƯU HÓA: Loại bỏ các phần Tác vụ nền hoặc Số liệu nếu dự án không hỗ trợ.
4. LÀM SẠCH: Xóa bỏ tất cả ghi chú in nghiêng và khối hướng dẫn này.

II. HƯỚNG DẪN TÙY BIẾN CHO NGƯỜI DÙNG:
1. ĐIỀN THÔNG TIN: Thay thế `[HOST]`, `[CỔNG]`, và `[đường-dẫn-health]` bằng chi tiết dịch vụ thực tế của bạn.
2. ĐIỀU CHỈNH: Tùy chỉnh bảng Xử lý sự cố với các lỗi thường gặp được phát hiện trong quá trình kiểm thử.
3. HOÀN THIỆN: Đảm bảo các lệnh vận hành (ví dụ: curl) chính xác với cấu trúc API của bạn. Xóa văn bản hướng dẫn (chữ *in nghiêng*) trước khi xuất bản.
-->

# Hướng dẫn Vận hành

Tài liệu này giải thích cách giám sát, kiểm tra và bảo trì **[Tên Dự án]** trong môi trường vận hành thực tế.

## Giám sát Sức khỏe

Truy cập giao diện kiểm tra sức khỏe để xác minh trạng thái hệ thống:

```bash
curl http://[HOST]:[CỔNG]/[đường-dẫn-health]
```

**Các hạng mục kiểm tra:**
- [ví dụ: Kết nối cơ sở dữ liệu]
- [ví dụ: Tính khả dụng của dịch vụ]

## Số liệu Hệ thống (Metrics)

Hiển thị và thu thập các số liệu hiệu năng (ví dụ: qua Prometheus):

```bash
curl http://[HOST]:[CỔNG]/[đường-dẫn-metrics]
```

**Các danh mục số liệu chính:**
- **Lưu lượng**: [ví dụ: Số lượng yêu cầu, thông lượng]
- **Độ trễ**: [ví dụ: Biểu đồ thời gian phản hồi]
- **Lỗi**: [ví dụ: Số lượng lỗi 4xx/5xx]

## Ghi nhật ký & Khả năng giám sát

Mô tả chiến lược ghi nhật ký và cách truy cập nhật ký hệ thống.

- **Định dạng Log chuẩn**: [ví dụ: JSON cấu trúc]
- **Phương thức truy cập**: [ví dụ: `docker logs` hoặc một hệ thống tập hợp log trung tâm]

## Bảo trì Định kỳ

*Hướng dẫn cho các tác vụ theo lịch trình, dọn dẹp dữ liệu hoặc cập nhật hệ thống.*

## Xử lý Sự cố (Cơ bản)

| Sự cố | Kiểm tra ban đầu | Hành động |
|---|---|---|
| **[Vấn đề 1]** | [Bước xác minh] | [Bước giải quyết] |
| **[Vấn đề 2]** | [Bước xác minh] | [Bước giải quyết] |

---

<div align="center">

[Quay lại Danh mục Tài liệu](README.md)

</div>
