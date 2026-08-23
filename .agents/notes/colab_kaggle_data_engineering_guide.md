# Sổ Tay Kỹ Thuật: Kinh Nghiệm Xử Lý Dữ Liệu Lớn Trên Google Colab & Kaggle (GPU & TPU)

Tài liệu này tổng hợp toàn bộ các kỹ thuật tối ưu hóa xử lý dữ liệu lớn (Big Data / Video / Multimodal Retrieval), các bài học kinh nghiệm thực chiến từ các cuộc thi AI quốc tế (Kaggle Grandmaster tricks, VBS, LSC) và các giải pháp đã được chứng minh trong dự án AIC 2026.

---

## 1. Bản Đồ Tổng Quan: So Sánh Môi Trường Colab vs Kaggle

| Tiêu Chí So Sánh | Google Colab | Kaggle Notebooks (GPU) | Kaggle Notebooks (TPU v3-8) |
| :--- | :--- | :--- | :--- |
| **Vai Trò Tối Ưu** | **Data Staging Hub**: Mount Drive, giải nén nhanh trên NVMe cục bộ, đóng gói `.blob`, đẩy sang Kaggle. | **End-to-End Pipeline**: TransNet V2, `faster-whisper` (CUDA), `EasyOCR`, xuất DB. | **Massive Batch Embedding**: Trích xuất ma trận vector SigLIP / CLIP với batch size cực lớn (2048+). |
| **Hạn Mức Bộ Nhớ VRAM** | 15GB (T4) / 40GB (A100). | **32GB (16GB x 2 Dual T4)**. | **128GB HBM (16GB x 8 Cores)**. |
| **Hạn Mức Thời Gian (Free Quota)** | Biến đổi (thường 4 - 12h/phiên). | **30 Giờ GPU / Tuần**. | **20 Giờ TPU / Tuần** (Hạn mức độc lập, không trừ vào GPU). |
| **Giới Hạn Ổ Đĩa (Disk Quota)** | ~100GB - 150GB SSD tạm trên `/content/`. | 20GB trên `/kaggle/working/` (Input vô hạn). | 20GB trên `/kaggle/working/` (Input vô hạn). |

> **Chiến Lược Nhân Đôi Quota (50 Giờ/Tuần/Account):**
> Sử dụng 30h GPU để xử lý các mô hình phụ thuộc nhân CUDA (`faster-whisper`, `EasyOCR`, `TransNet V2`). Sử dụng 20h TPU hoàn toàn độc lập để trích xuất vector nhúng ảnh và văn bản SigLIP Base quy mô lớn.

---

## 2. Các Kinh Nghiệm & Kỹ Thuật Tối Ưu Trên Google Colab

### 2.1. Khắc Phục Nghẽn Cổ Chai I/O Của Google Drive (The FUSE Bottleneck)
- **Vấn Đề:** Khi mount Google Drive (`/content/drive`), hệ thống sử dụng giao thức FUSE (Filesystem in Userspace). Việc đọc lặp qua hàng nghìn file ảnh nhỏ trực tiếp trên `/content/drive` sẽ làm giảm tốc độ đọc từ 50 đến 100 lần, thường xuyên bị treo (I/O hang) hoặc ngắt kết nối.
- **Giải Pháp Chuẩn:**
  1. **Luôn copy tệp nén lớn sang SSD cục bộ của Colab trước:**
     ```python
     !cp /content/drive/MyDrive/AIC2026/Videos_L21_a.zip /content/
     !unzip -q /content/Videos_L21_a.zip -d /content/raw_videos/
     ```
  2. Thực hiện toàn bộ các thao tác xử lý trên `/content/raw_videos/` (tốc độ đọc NVMe Colab đạt 1.5 - 2.5 GB/s).
  3. Chỉ copy tệp kết quả cuối cùng trở lại Google Drive.

### 2.2. Kỹ Thuật Đóng Gói Tệp Nhị Phân Contiguous (`.blob` / `ZIP_STORED`)
- **Vấn Đề:** Khi tải 100,000 ảnh keyframes lên Kaggle, hệ thống Kaggle sẽ mất hàng giờ để quét số lượng file (inode indexing) và có thể tự động giải nén làm tràn đĩa.
- **Giải Pháp Chuẩn:**
  - Gom toàn bộ ảnh vào một file duy nhất với chuẩn `zipfile.ZIP_STORED` (không nén thuật toán để CPU giải mã với chi phí 0%):
    ```python
    import zipfile, glob, os
    with zipfile.ZipFile("/content/keyframes.blob", "w", zipfile.ZIP_STORED) as zf:
        for img in glob.glob("/content/extracted/**/*.jpg", recursive=True):
            arcname = os.path.relpath(img, "/content/extracted")
            zf.write(img, arcname)
    ```
  - Đặt tên đuôi là `.blob` để Kaggle không tự động giải nén khi gắn vào Dataset.

### 2.3. Tận Dụng Băng Thông Cloud Đẩy Dữ Liệu Lên Kaggle API
- **Giải Pháp Chuẩn:** Đẩy dữ liệu trực tiếp từ Colab lên Kaggle Dataset qua Kaggle API. Tận dụng mạng cáp quang nội bộ Google Cloud, một file 10GB chỉ mất 30 - 60 giây để upload.

---

## 3. Các Kinh Nghiệm & Kỹ Thuật Tối Ưu Trên Kaggle Notebooks (GPU)

### 3.1. Chiến Thuật Vượt Giới Hạn Ổ Đĩa 20GB (Zero Disk Waste Strategy)
- **Nguyên Tắc:** `/kaggle/input/` là vùng đọc Read-Only KHÔNG TÍNH vào 20GB giới hạn.
- **Quy Tắc Thực Hành:**
  1. Video được đọc luồng trực tiếp (`cv2.VideoCapture("/kaggle/input/.../video.mp4")`).
  2. Keyframe trong `.blob` được đọc trực tiếp vào RAM theo dạng bytes (`Image.open(io.BytesIO(raw_bytes))`).
  3. Thư mục `/kaggle/working/` chỉ chứa 2 tệp xuất bản cuối cùng: `runtime.sqlite` và `siglip.faiss` (< 1GB tổng dung lượng).

### 3.2. Khai Thác Song Song Dual GPU T4 (Multi-GPU Parallelism)
- Bọc mô hình SigLIP Base bằng `torch.nn.DataParallel(model)` khi trích xuất vector batch, hoặc phân luồng xử lý ASR trên `cuda:1` và Visual Feature trên `cuda:0`.

### 3.3. Tăng Tốc Cài Đặt Thư Viện Bằng `uv`
- Sử dụng `uv pip install --system ...` thay cho `pip install` thông thường, rút ngắn thời gian cài thư viện từ 3 phút xuống **12 giây**.

---

## 4. Khai Thác Sức Mạnh Kaggle TPU v3-8 (Tensor Processing Unit)

TPU v3-8 cung cấp 8 nhân xử lý ma trận độc lập với 128GB HBM. Đây là vũ khí tối thượng để xử lý các phép toán nhân ma trận lớn (Dense Vector Batch Extraction).

### 4.1. Cách Kích Hoạt TPU v3-8 Trên Kaggle
1. Trong bảng **Settings** bên phải của Kaggle Notebook:
   - **Accelerator:** Chọn **TPU VM v3-8**.
   - **Internet:** Bật **ON**.
2. Kiểm tra kết nối PyTorch/XLA:
   ```python
   import torch_xla.core.xla_model as xm
   device = xm.xla_device()
   print("Thiết bị TPU khả dụng:", device)
   ```

### 4.2. Trích Xuất Vector SigLIP Siêu Tốc Trên 8 Nhân TPU (XMP Multi-Processing)
Sử dụng `torch_xla.distributed.xla_multiprocessing` để phân bổ 100,000 khung hình cho 8 nhân TPU xử lý song song với tốc độ gấp **5 - 10 lần** so với GPU đơn:

```python
import torch_xla.distributed.xla_multiprocessing as xmp
import torch_xla.core.xla_model as xm

def _mp_extract_vectors(rank, image_paths_chunk, model_name):
    device = xm.xla_device()
    processor = AutoProcessor.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name).to(device)
    model.eval()

    # XLA tối ưu nhất với kích thước Tensor cố định (Fixed Batch Size)
    BATCH_SIZE = 256 # 256 ảnh/core x 8 cores = 2048 ảnh/lượt
    # ... Vòng lặp trích xuất và lưu ma trận vector ...
    xm.mark_step() # Đồng bộ hóa tính toán trên TPU graph
```

### 4.3. Lưu Ý Kỹ Thuật Khi Sử Dụng TPU (XLA Compilation Rules)
1. **Tránh Dynamic Tensor Shapes (Kích thước tensor thay đổi liên tục):**
   - Trình biên dịch XLA sẽ phải biên dịch lại (recompile) đồ thị tính toán mỗi khi kích thước batch thay đổi, gây tụt hiệu năng.
   - **Quy tắc:** Luôn pad hoặc cắt ảnh về đúng kích thước cố định `(224, 224)` và giữ nguyên kích thước `BATCH_SIZE` cố định trong suốt quá trình chạy.
2. **Các Thư Viện Không Chạy Trên TPU:**
   - Các thư viện viết riêng cho NVIDIA CUDA như `faster-whisper` (CTranslate2) hoặc `faiss-gpu` không thể chạy trên TPU Core (chỉ chạy trên CPU host của TPU VM). Vì vậy, hãy chia việc: Dùng TPU cho SigLIP Vector / CLIP / VLM; dùng GPU cho Whisper ASR & OCR.

---

## 5. Bảng Kiểm Tra Sẵn Sàng (Preflight Checklist)

- [ ] Đã kiểm tra hạn mức GPU (30h) và TPU (20h) trên Kaggle Profile.
- [ ] Đã bật `Internet: ON` và cấu hình `HF_TOKEN` / `KAGGLE_KEY` trong Kaggle Secrets.
- [ ] Không giải nén dữ liệu bừa bãi vào `/kaggle/working/` (Giữ nguyên tắc Zero Disk Waste).
- [ ] Đã chọn đúng phần cứng cho từng tác vụ: GPU cho ASR/OCR/Shot Detection, TPU cho SigLIP Vector Batch Inference.
- [ ] Gói phát hành cuối cùng `release_artifacts.zip` được nén chuẩn `ZIP_DEFLATED` sẵn sàng tải về máy thi đấu.
