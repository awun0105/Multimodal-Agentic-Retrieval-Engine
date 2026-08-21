# Kaggle MVP Runner - Multimodal Agentic Retrieval Engine

Thư mục này chứa toàn bộ mã nguồn và kịch bản (scripts) để chạy ứng dụng **MVP (Minimum Viable Product)** của hệ thống tìm kiếm đa phương tiện trên môi trường **Kaggle Notebook** sử dụng GPU kép (T4 x2).

## Tính năng cốt lõi (Đã tối ưu riêng cho Kaggle)

Hệ thống gốc đã được tinh chỉnh (monkey-patch) tự động thông qua file `kaggle_mvp_runner.py` nhằm vượt qua các giới hạn khắt khe của Kaggle:

1. **Đọc ảnh trực tiếp từ `.blob` siêu nén:** Thay vì phải giải nén hàng chục nghìn bức ảnh ra đĩa (điều sẽ làm tràn bộ nhớ 20GB của Kaggle), hệ thống sử dụng `VirtualBlobReader` để truy xuất ảnh trực tiếp vào RAM, tối đa hóa tốc độ đọc.
2. **Tiền xử lý Vector FAISS:** Tự động đọc file `.faiss`, trích xuất các vector thô và lưu dưới dạng `.npy` Memory-Mapped. Giúp tăng tốc quá trình tính toán khoảng cách cosine mà không sợ bị tràn RAM (OOM).
3. **Multi-GPU Concurrency (T4 x2):** Ghi đè bộ máy tìm kiếm gốc bằng `MultiGPUCLIPSearcher`. Thuật toán sẽ điều phối truy vấn của người dùng luân phiên (Round-Robin) lên cả 2 card T4, tăng gấp đôi lượng truy cập đồng thời từ Gradio.
4. **Lazy Load & Offline Mode (Khởi động nhanh & Tránh Treo):** Các mô hình Trí Tuệ Nhân Tạo được nạp lười (lazy-load) trong lần truy vấn đầu tiên thay vì nạp trước. App ép buộc chạy chế độ Offline (không kết nối HuggingFace) để tránh tình trạng treo (hang) do Rate Limit.
5. **Auto-Shutdown 10 phút:** Ứng dụng sẽ tự động tắt máy chủ Gradio sau 10 phút khởi chạy để giải phóng tài nguyên. Tránh treo session dài lãng phí GPU.

---

## 🛠 Hướng Dẫn Sử Dụng Trên Kaggle

### Bước 1: Chuẩn bị Kaggle Notebook
1. Tạo một Notebook mới trên Kaggle.
2. Tại bảng cài đặt bên phải (Settings):
   - **Accelerator:** Chọn **GPU T4 x2**.
   - **Internet:** Bật **ON** (Cần thiết để tải thư viện và mô hình lần đầu).
3. Thêm Dataset vào Notebook:
   - Click **"Add Input"** -> Tìm kiếm Dataset: `nhathoang42/aic2025-mvp-app-data`.
   - Tìm kiếm Dataset mã nguồn: `nhathoang42/mvp-app-code`.
   - Bấm nút **"+"** để gắn 2 Dataset này vào Notebook của bạn.
   - *Lưu ý: Dataset data phải chứa file `.blob` và `.faiss`.*

### Bước 2: Chạy ứng dụng
1. File chạy chính đã được đóng gói sẵn trong `mvp-app-code` dưới dạng **`kaggle_mvp_runner.ipynb`**.
2. Bạn có thể mở file này trong Kaggle, kiểm tra mã, và bấm **"Run All"**.

### Bước 3: Truy cập Giao diện Web (Gradio)
Sau khi load FAISS và metadata (khoảng 30 giây), hệ thống sẽ in ra dòng:
```
[TIEN TRINH] Khoi chay ung dung MVP App...
Running on public URL: https://xxxx.gradio.live
```
Bấm vào đường link `xxxx.gradio.live` để trải nghiệm tìm kiếm hình ảnh đa phương thức với sức mạnh của cụm GPU T4 x2! (Lần tìm kiếm đầu tiên sẽ chậm hơn do Lazy Load CLIP lên 2 GPU, khoảng 30s-1p. Các lần sau sẽ rất nhanh).

---

## ⚙️ Cấu Trúc Thư Mục

- `mvp-app.tar`: Chứa mã nguồn MVP gốc của hệ thống (như `app.py`, `clip.py`, `db.py`, v.v.). Các file này được giải nén lúc runtime để đồng bộ dễ dàng.
- `kaggle_mvp_runner.py`: Kịch bản điều phối trung tâm. Nó chịu trách nhiệm cài đặt thư viện, giải nén dữ liệu, và patch (chắp vá) mã nguồn gốc lúc runtime để thích ứng với Kaggle.
- `kaggle_mvp_runner.ipynb`: Phiên bản Notebook của runner, thân thiện với giao diện Kaggle.
- `test_parallel.py`: Kịch bản kiểm thử cục bộ. Dùng để gửi 2 yêu cầu truy vấn cùng lúc nhằm xác nhận cơ chế đa luồng (Multi-GPU) đang hoạt động ổn định.

## 🔗 Liên kết dữ liệu

- **Kaggle Dataset Code:** [mvp-app-code](https://www.kaggle.com/datasets/nhathoang42/mvp-app-code)
- **Kaggle Dataset Data:** [aic2025-mvp-app-data](https://www.kaggle.com/datasets/nhathoang42/aic2025-mvp-app-data)

