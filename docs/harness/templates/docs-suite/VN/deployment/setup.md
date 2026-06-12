<!-- 
BẢN MẪU TÀI LIỆU: Thiết lập Production
======================================
Trọng tâm: Quy trình từng bước để triển khai lên môi trường vận hành thực tế.

I. GIAO THỨC THỰC THI CHO AGENT (DÀNH CHO AI):
1. THU THẬP NGỮ CẢNH: Quét các bản kê triển khai (Dockerfile, docker-compose.yml, helm charts) và các script hạ tầng.
2. ĐIỀN DỮ LIỆU: Thay thế các thuật ngữ trong dấu ngoặc vuông `[ ]` bằng runtime production, cổng và các lệnh CLI cụ thể.
3. TỐI ƯU HÓA: Loại bỏ các phần đặc thù của nền tảng (ví dụ: Kubernetes) nếu chỉ hỗ trợ Docker.
4. LÀM SẠCH: Xóa bỏ tất cả ghi chú in nghiêng và khối hướng dẫn này.

II. HƯỚNG DẪN TÙY BIẾN CHO NGƯỜI DÙNG:
1. ĐIỀN THÔNG TIN: Thay thế các nhãn chung như `[Runtime]` và `[docker-compose up -d]` bằng các lệnh thực tế của dự án.
2. ĐIỀU CHỈNH: Thêm các phần cho các nhà cung cấp Cloud cụ thể (AWS, Azure, GCP) nếu có.
3. HOÀN THIỆN: Xác minh rằng các bước triển khai đã được kiểm thử và chính xác cho một lần cài đặt sạch. Xóa văn bản hướng dẫn (chữ *in nghiêng*) trước khi xuất bản.
-->

# Thiết lập Production

Hướng dẫn này cung cấp một quy trình chuẩn để triển khai **[Tên Dự án]** vào môi trường vận hành thực tế.

## 1. Yêu cầu Hệ thống
- **Runtime**: [ví dụ: Docker, Node.js, Python runtime]
- **Phần cứng**: [Liên kết đến Yêu cầu Phần cứng trong README]
- **Mạng**: [ví dụ: Mở cổng cho HTTP/HTTPS, cấu hình VPC]

## 2. Chuẩn bị Hạ tầng
*Hướng dẫn thiết lập các máy chủ cần thiết, cơ sở dữ liệu được quản lý, hoặc các tài nguyên đám mây.*

## 3. Cấu hình & Bí mật (Secrets)
1.  Khởi tạo tệp môi trường production (`[ví dụ: .env.production]`).
2.  Điền tất cả các thông tin xác thực nhạy cảm (API keys, mật khẩu DB) vào trình quản lý bí mật bảo mật hoặc tệp môi trường.

## 4. Thực thi / Triển khai
*Hướng dẫn xây dựng và khởi chạy ứng dụng.*

```bash
# Ví dụ lệnh triển khai
[ví dụ: docker-compose up -d]
```

## 5. Kiểm tra Sức khỏe & Xác minh
*Các bước chi tiết để xác minh hệ thống hoạt động hoàn hảo sau khi triển khai.*

---

<div align="center">

[Quay lại Danh mục Tài liệu](../README.md)

</div>
