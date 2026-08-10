# Phân hệ Nghiên cứu & Trích xuất Multimodal Embedding

Thư mục này là **Trụ cột 1** trong định hướng nghiên cứu của dự án *Multimodal Agentic Retrieval Engine* (AIC 2026).
Nhiệm vụ chính của phân hệ này là đo lường, đánh giá và hiện thực hóa một bộ trích xuất đặc trưng (Embedding Extractor) tối ưu nhất, phục vụ trực tiếp cho Tầng 1 (Base Pipeline - FAISS Indexing).

---

## 1. Cấu Trúc Phân Hệ

```text
system1/research/embedding/
├── plan_and_status.md                  # BẢN ĐỒ NGHIÊN CỨU & TRẠNG THÁI (Đọc file này đầu tiên)
├── README.md                           # Tài liệu tổng quan (Bạn đang đọc)
├── benchmark_testing/                  # Thư mục cốt lõi chứa các bài Benchmark quy mô lớn
│   ├── README.md                       # Tài liệu hướng dẫn sử dụng các bản benchmark
│   ├── colab_data_prep.ipynb           # Script nén Virtual Cache (.blob) trên Colab
│   ├── kaggle_benchmark.ipynb          # Benchmark 24 mô hình (Phương pháp truyền thống)
│   ├── kaggle_benchmark_blob.ipynb     # Benchmark 24 mô hình (Phương pháp tối ưu I/O)
│   └── colab_benchmark.ipynb           # Benchmark dự phòng (Fallback cho 1 GPU T4)
├── extractor.py                        # Module Lõi: Trừu tượng hóa mô hình thành hàm `get_vector()`
├── main.py                             # Giao diện dòng lệnh (CLI Runner) để kiểm thử Module Lõi
└── README.md                           # Tài liệu tổng quan (Bạn đang đọc)
```

---

## 2. Định Hướng & Trạng Thái (Kế hoạch Nghiên cứu)

Quá trình R&D (Nghiên cứu & Phát triển) tại đây tuân theo lộ trình 4 bước khắt khe (tham khảo chi tiết tại `plan_and_status.md`):

1. **Phase 1: Đo lường Tốc độ & Dung lượng (Speed & VRAM Benchmark) - ĐÃ HOÀN THÀNH**
   - Đánh giá 24 mô hình SOTA trên nền tảng Kaggle Dual-GPU.
   - Các kịch bản chạy nằm trong thư mục con `benchmark_testing/`.

2. **Phase 2: Đánh giá Độ chính xác (Accuracy Benchmark) - SẮP DIỄN RA**
   - Lọc Top mô hình xuất sắc nhất từ Phase 1.
   - Chạy kiểm thử độ chính xác (Cosine Similarity, Recall@K) trên tập dữ liệu có gán nhãn.

3. **Phase 3: Hiện thực hóa Hàm Lõi (Core Function Integration) - ĐANG THỰC HIỆN**
   - Đóng gói mô hình tối ưu vào `extractor.py` thông qua hàm `get_vector()`.
   - Script `main.py` được sử dụng để kiểm thử tính đúng đắn của chuẩn hóa L2 và cấu trúc tensor.

4. **Phase 4: Tối ưu Cục bộ (CPU-only / Local-first) - SẮP DIỄN RA**
   - Lượng tử hóa mô hình sang định dạng ONNX/OpenVINO để có thể chạy mượt trên CPU truyền thống, phục vụ vòng chung kết thi Offline.

---

## 3. Hướng Dẫn Sử Dụng Module Lõi (`extractor.py`)

Module `extractor.py` cung cấp giao diện lập trình chuẩn hóa (API) để tích hợp vào các hệ thống khác (như FAISS Indexing Pipeline). Mọi vector đầu ra đều được tự động chuẩn hóa L2 (L2-Normalized).

```python
from extractor import get_vector
from pathlib import Path

# 1. Trích xuất từ đường dẫn ảnh
img_path = Path("data/sample_keyframes/frame_001.jpg")
image_vector = get_vector(img_path)

# 2. Trích xuất từ đoạn văn bản (Text Query)
text_query = "cầu thủ mặc áo đỏ đang sút bóng"
text_vector = get_vector(text_query)

# (Đảm bảo image_vector.shape == text_vector.shape)
```

**Để chạy kiểm thử nhanh luồng này:**
```bash
python main.py
```
