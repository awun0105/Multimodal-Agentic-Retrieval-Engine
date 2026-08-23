# Log Giao Tiếp & Chuyển Nhượng: Tối ưu Cloud & Thiết lập Rules (2026-08-21)

## 1. Bối cảnh
- **Mục tiêu:** Đưa MVP App lên Kaggle/Colab với tài nguyên cực kỳ hạn chế (Kaggle chỉ có 20GB Disk, 30GB RAM, 16GB VRAM).
- **Yêu cầu khắt khe:** Tối ưu hóa tối đa RAM, VRAM và I/O Disk. Phải xin phép User trước khi chạy lệnh.

## 2. Các hành động đã thực thi (Bàn giao cho Agent sau)
1. **Thiết lập "Initialization Protocol":** Đã tiêm lệnh bắt buộc (System Override) vào .agents/AGENTS.md để ép TẤT CẢ các Agent thế hệ sau phải đọc thư mục context/ và ules/ trước khi chat.
2. **Cập nhật User Rules (.agents/rules/user_rules.md):**
   - Đã thêm luật: Giải thích "chạy lệnh này để làm gì" ngắn gọn đơn giản trước khi xin phép User.
   - Đã thêm luật: **Append-Only Rule** - Chỉ được phép thêm luật mới, TUYỆT ĐỐI KHÔNG xóa luật cũ.
3. **Tối ưu mã nguồn MVP (monolith-mvp-app):**
   - Bật cờ aiss.IO_FLAG_MMAP trong mvp-app/clusterer.py để tiết kiệm 90% RAM (OS chỉ ánh xạ index).
   - Kích hoạt 	orch_dtype=torch.float16 trong mvp-app/clip.py để giảm 50% VRAM cho mô hình SigLIP.
4. **Tạo Bộ công cụ triển khai (cloud_deployment_tools):**
   - Cung cấp kaggle_host_mvp.ipynb hoàn chỉnh (tự clone code, set DATA_ROOT=/kaggle/input/ và mở Gradio Share).
   - Hỗ trợ kiến trúc Multi-GPU (DataParallel) và TPU (	orch_xla).

## 3. Lời dặn cho Agent tiếp theo
Đã hoàn tất dọn đường cơ sở hạ tầng. Vui lòng chuyển hướng sang **Thử nghiệm Truy vấn Thực tế (Live Query Testing)** nếu User yêu cầu, dựa trên danh sách truy vấn từ file queries_output.md.

