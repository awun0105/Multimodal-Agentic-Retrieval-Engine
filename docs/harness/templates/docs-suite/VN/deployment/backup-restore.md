<!-- 
BẢN MẪU TÀI LIỆU: Sao lưu và Phục hồi
====================================
Trọng tâm: Bảo tồn trạng thái, an toàn dữ liệu và quy trình phục hồi sau sự cố.

I. GIAO THỨC THỰC THI CHO AGENT (DÀNH CHO AI):
1. THU THẬP NGỮ CẢNH: Xác định các thành phần có trạng thái quan trọng (cơ sở dữ liệu, lưu trữ đối tượng, tệp cấu hình) và các script hoặc công cụ sao lưu hiện có.
2. ĐIỀN DỮ LIỆU: Thay thế văn bản trong dấu ngoặc vuông `[ ]` bằng các công cụ và lệnh CLI chính xác dùng để dump và restore dữ liệu.
3. TỐI ƯU HÓA: Loại bỏ các phần nếu dự án là stateless hoặc sử dụng các dịch vụ sao lưu được quản lý hoàn toàn.
4. LÀM SẠCH: Xóa bỏ tất cả ghi chú in nghiêng và khối hướng dẫn này.

II. HƯỚNG DẪN TÙY BIẾN CHO NGƯỜI DÙNG:
1. ĐIỀN THÔNG TIN: Cung cấp các ví dụ CLI đã được kiểm thử cho backend cơ sở dữ liệu và lưu trữ cụ thể của dự án.
2. ĐIỀU CHỈNH: Xác định tần suất "Chiến lược Sao lưu" rõ ràng (ví dụ: hàng ngày, hàng giờ).
3. HOÀN THIỆN: Đảm bảo các bước phục hồi đã được xác minh. Xóa văn bản hướng dẫn (chữ *in nghiêng*) trước khi xuất bản.
-->

# Sao lưu và Phục hồi

Các quy trình bảo tồn trạng thái và phục hồi sau sự cố cho **[Tên Dự án]**.

## Chiến lược Sao lưu

- **Cơ sở dữ liệu**: [ví dụ: pg_dump hàng ngày].
- **Lưu trữ đối tượng**: [ví dụ: rclone sync sang S3].
- **Cấu hình**: [ví dụ: Lưu trữ bí mật đã mã hóa].

## Kiểm tra Phục hồi

### 1. Phục hồi Cơ sở dữ liệu
```bash
# Ví dụ lệnh thực hiện
psql -U [user] [tên_db] < backup.sql
```

### 2. Phục hồi Lưu trữ đối tượng
*Hướng dẫn khôi phục các tệp tin/dữ liệu nhị phân.*

## Kiểm tra Tự động
*Giải thích các script hoặc cron jobs dùng để xác minh tính toàn vẹn của bản sao lưu.*

---

<div align="center">

[Quay lại Danh mục Tài liệu](../README.md)

</div>
