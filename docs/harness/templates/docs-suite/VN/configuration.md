<!-- 
BẢN MẪU TÀI LIỆU: Cấu hình
=========================
Trọng tâm: Chi tiết về các biến môi trường, thiết lập nội bộ và quản lý thông tin xác thực.

I. GIAO THỨC THỰC THI CHO AGENT (DÀNH CHO AI):
1. THU THẬP NGỮ CẢNH: Quét mã nguồn để tìm các tệp mẫu môi trường (.env.example), các lớp cấu hình và các phụ thuộc bí mật bên ngoài.
2. ĐIỀN DỮ LIỆU: Thay thế các nhãn trong dấu ngoặc vuông `[ ]` bằng các nhóm biến và mô tả cụ thể của dự án.
3. TỐI ƯU HÓA: Loại bỏ các danh mục cấu hình (ví dụ: Logging) nếu chúng được xử lý ngầm định.
4. LÀM SẠCH: Xóa bỏ tất cả ghi chú in nghiêng và khối hướng dẫn này.

II. HƯỚNG DẪN TÙY BIẾN CHO NGƯỜI DÙNG:
1. ĐIỀN THÔNG TIN: Cập nhật các bảng thiết lập với các biến môi trường thực tế và giá trị mặc định của dự án.
2. ĐIỀU CHỈNH: Thêm hoặc bớt các nhóm dựa trên độ phức tạp của dịch vụ (ví dụ: thêm phần "API bên thứ ba").
3. HOÀN THIỆN: Đảm bảo tất cả các key nhạy cảm được tài liệu hóa dưới dạng placeholder và không bao giờ được viết trực tiếp (hardcoded). Xóa văn bản hướng dẫn (chữ *in nghiêng*) trước khi xuất bản.
-->

# Cấu hình

Tài liệu này bao gồm các tùy chọn cấu hình cho **[Tên Dự án]**, cung cấp bản đồ các biến môi trường và thiết lập nội bộ.

## Các tệp cấu hình

- **Phát triển**: [ví dụ: .env]
- **Production**: [ví dụ: .env.production hoặc Kubernetes Secrets]

## Danh mục thiết lập

### 1. Cốt lõi Ứng dụng
| Biến | Mô tả | Mặc định |
|---|---|---|
| `[APP_VAR_1]` | [Mô tả] | [Giá trị mặc định] |
| `[APP_VAR_2]` | [Mô tả] | [Giá trị mặc định] |

### 2. Cơ sở dữ liệu & Dịch vụ bên ngoài
*Chi tiết về chuỗi kết nối, endpoint và thông tin xác thực cho tất cả các dịch vụ có trạng thái.*

### 3. Bảo mật & Xác thực
*Thiết lập cho API keys, bí mật mã hóa, tokens và chính sách CORS.*

### 4. Ghi nhật ký (Logging) & Giám sát
*Cấp độ log, khoảng thời gian thu thập số liệu và các endpoint đo lường.*

---

<div align="center">

[Quay lại Danh mục Tài liệu](README.md)

</div>
