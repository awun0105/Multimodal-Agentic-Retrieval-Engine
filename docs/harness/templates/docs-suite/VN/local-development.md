<!-- 
BẢN MẪU TÀI LIỆU: Phát triển cục bộ
=================================
Trọng tâm: Thiết lập môi trường, quản lý thư viện và kiểm thử/gỡ lỗi cục bộ.

I. GIAO THỨC THỰC THI CHO AGENT (DÀNH CHO AI):
1. THU THẬP NGỮ CẢNH: Xác định runtime yêu cầu (Python, Node, v.v.), các tệp quản lý thư viện và hạ tầng cục bộ (ví dụ: dev docker-compose).
2. ĐIỀN DỮ LIỆU: Thay thế văn bản trong dấu ngoặc vuông `[ ]` bằng các lệnh CLI thực tế để tạo môi trường và cài đặt thư viện.
3. TỐI ƯU HÓA: Loại bỏ các phần như "Linting" nếu không có công cụ nào được cấu hình trong kho mã nguồn.
4. LÀM SẠCH: Xóa bỏ tất cả ghi chú in nghiêng và khối hướng dẫn này.

II. HƯỚNG DẪN TÙY BIẾN CHO NGƯỜI DÙNG:
1. ĐIỀN THÔNG TIN: Cập nhật hướng dẫn với các lệnh thiết lập đã được kiểm thử của bạn (ví dụ: `npm install` hoặc `pip install`).
2. ĐIỀU CHỈNH: Thêm các ghi chú cụ thể về cấu hình IDE hoặc các công cụ gỡ lỗi cục bộ mà đội ngũ của bạn sử dụng.
3. HOÀN THIỆN: Đảm bảo phần "Chạy ứng dụng tại máy cá nhân" đơn giản và hoạt động được ngay sau khi clone mã nguồn. Xóa văn bản hướng dẫn (chữ *in nghiêng*) trước khi xuất bản.
-->

# Phát triển Cục bộ

Hướng dẫn này giải thích cách thiết lập **[Tên Dự án]** để phát triển, kiểm thử và gỡ lỗi tại máy cá nhân.

## 1. Điều kiện tiên quyết
- [ví dụ: Python 3.11+, Node.js 18+]
- [ví dụ: Công cụ quản lý môi trường ảo: venv, uv, hoặc conda]

## 2. Các bước thiết lập
1.  **Môi trường**: Tạo và kích hoạt môi trường ảo.
2.  **Thư viện**: Cài đặt các thư viện phụ thuộc cho phát triển.
    ```bash
    [ví dụ: pip install -r requirements-dev.txt]
    ```
3.  **Dịch vụ cục bộ**: Khởi chạy hạ tầng cục bộ (ví dụ: qua `docker-compose.dev.yml`).

## 3. Chạy ứng dụng tại máy cá nhân
*Hướng dẫn chạy server hoặc tiến trình chính trong chế độ debug.*

## 4. Kiểm thử (Testing)
*Các lệnh để chạy unit test và integration test.*

## 5. Linting và Định dạng
*Hướng dẫn sử dụng các công cụ như Ruff, ESLint, hoặc Prettier.*

---

<div align="center">

[Quay lại Danh mục Tài liệu](README.md)

</div>
