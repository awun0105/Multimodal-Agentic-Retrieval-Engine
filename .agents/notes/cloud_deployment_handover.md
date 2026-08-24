# Handover Note: Cloud Deployment Tools (Kaggle & Colab)

## Cập nhật trạng thái
- Đã tạo thư mục cloud_deployment_tools (đổi tên từ New folder cũ).
- Đã tổng hợp các script triển khai cloud thành định dạng .ipynb chuẩn chuyên nghiệp.

## Kiến trúc cần lưu ý cho các Agent sau
1. **Virtual Cache Pattern (.blob):** Hệ thống dùng file .blob (ZIP_STORED) để lưu ảnh. Không bao giờ giải nén ảnh ra disk trên Kaggle. Dùng BytesIO để đọc thẳng vào RAM -> VRAM.
2. **Kaggle Hardware:** 
   - Đã hỗ trợ **Dual T4 GPU** (dùng DataParallel cho batching 64-128).
   - Đã hỗ trợ **TPU v5e-8** (dùng thư viện 	orch_xla, batching cực lớn 512-2048).
3. **App Hosting:** 
   - Có thể chạy giao diện MVP trực tiếp trên Kaggle Notebook bằng cờ share=True trong Gradio.

## User Rules mới
- Luôn phải **thông báo và giải thích tóm tắt các bước** sắp làm trước khi yêu cầu User xác nhận chạy lệnh.
- Lưu ý ghi chú chuyên nghiệp (Document code) trong các file triển khai.

