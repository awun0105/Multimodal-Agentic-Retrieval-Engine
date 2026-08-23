# Kiến Trúc Phần Cứng & Quy Chuẩn Vận Hành Trên Nền Tảng Kaggle (Kaggle Hardware & Execution Architecture)

Tài liệu này xác lập quy chuẩn kỹ thuật phần cứng, phân tầng tài nguyên điện toán (Compute Tiers), cấu trúc lưu trữ và quy tắc vận hành cho phân hệ Multimodal Embedding trong dự án AIC 2026.

---

## 1. Chiến Lược Phân Tầng Điện Toán (3-Tier Compute Strategy)

Để tối ưu hóa thời gian phát triển và hiệu năng khai thác trên các nền tảng đám mây (Kaggle/Colab) lẫn máy trạm thi đấu cục bộ, hệ thống phân định rõ vai trò của từng tầng phần cứng:

```
+-------------------------------------------------------------------------------+
| TIER 1: R&D & BENCHMARK ĐA MÔ HÌNH (Kaggle Dual T4 GPU)                       |
| - Mục tiêu: Đo đạc tốc độ, VRAM và độ chính xác trên 24 mô hình SOTA (Phases 1-2)|
| - Ưu điểm: Tương thích 100% CUDA, chạy mượt mọi thư viện Open-source          |
+---------------------------------------+---------------------------------------+
                                        | (Chọn ra 1 Quán quân duy nhất)
                                        v
+-------------------------------------------------------------------------------+
| TIER 2: SẢN XUẤT & TRÍCH XUẤT HÀNG LOẠT (Google TPU v5e-8 / Large GPU)        |
| - Mục tiêu: Băm 1.000.000+ Keyframes sang Vector FAISS index (Phase 3)         |
| - Ưu điểm: Năng lực ~1.57 PFLOPS, 128GB HBM2e, rút ngắn từ 20h xuống < 1h     |
+---------------------------------------+---------------------------------------+
                                        | (Đóng gói & Lượng tử hóa)
                                        v
+-------------------------------------------------------------------------------+
| TIER 3: TRIỂN KHAI CỤC BỘ / THI OFFLINE (Local CPU & Mobile GPU)              |
| - Mục tiêu: Truy xuất thời gian thực dưới 50ms cho người dùng tại hội trường  |
| - Tối ưu: Lượng tử hóa ONNX Runtime / OpenVINO / INT8, bộ nhớ đệm FAISS SQLite|
+-------------------------------------------------------------------------------+
```

---

## 2. Bảng Đối Chiếu Thông Số Kỹ Thuật Phần Cứng

| Tiêu chí | Tier 1: Dual GPU T4 (Kaggle) | Tier 2: TPU v5e-8 (Kaggle/Colab) | Tier 3: Local CPU / Edge GPU |
| :--- | :--- | :--- | :--- |
| **Nền tảng kiến trúc** | NVIDIA Turing (12nm) | Google TPU v5e (5nm) | Intel/AMD x86_64 / RTX Mobile |
| **Năng lực tính toán (BF16/FP16)** | ~130 TFLOPS (Tổng 2 card) | **~1.570 TFLOPS (~1.57 PFLOPS)** | ~5 - 30 TFLOPS |
| **Dung lượng Bộ nhớ** | 32 GB GDDR6 (16GB x 2) | **128 GB HBM2e (16GB x 8)** | 16 GB - 32 GB RAM hệ thống |
| **Băng thông bộ nhớ** | ~300 GB/s mỗi card | **~819 GB/s mỗi chip (HBM2e)** | ~50 - 100 GB/s (DDR4/DDR5) |
| **Batch Size tối ưu (Image)** | 64 - 128 (Dual-GPU Parallel) | **512 - 2048 (Data-Parallel)** | 1 - 16 (Tối ưu độ trễ đơn lẻ) |
| **Môi trường lập trình** | PyTorch / CUDA 12.x | PyTorch-XLA / JAX / Flax | ONNX Runtime / OpenVINO C++ |
| **Mục đích sử dụng chính** | Vòng loại Benchmark (Phases 1 & 2) | Trích xuất toàn bộ Keyframe (Phase 3) | Runtime thi đấu chính thức (Phase 4) |

---

## 3. Cấu Trúc Lưu Trữ Bất Biến & Topology I/O Trên Kaggle

Môi trường Kaggle Notebooks áp đặt giới hạn dung lượng nghiêm ngặt (**tối đa 20GB tại `/kaggle/working`**). Để đảm bảo không bao giờ gặp lỗi tràn đĩa (*Disk Quota Exceeded*) hoặc nghẽn đọc đĩa (*I/O Bottleneck*), hệ thống tuân thủ cấu trúc topology sau:

```
[Kaggle Dataset (/kaggle/input/)]
  |-- nhathoang42/aic2025-keyframes-blob/
        |-- cached_keyframes.blob (Tệp nhị phân nén ZIP_STORED)
                 │
                 │ (1. Đọc stream nhị phân trực tiếp bằng zipfile)
                 ▼
         [RAM / VRAM GPU (Dual T4)]
                 │
                 │ (2. Băm ra Vector L2-normalized)
                 ▼
         [Ma trận tương đồng (Cosine Similarity)]
                 │
                 │ (3. Chỉ ghi file báo cáo số liệu nhẹ < 5MB)
                 ▼
[Kaggle Output (/kaggle/working/)]
  |-- phase2_accuracy_report.md
  |-- phase2_accuracy_metrics.json
  `-- phase2_accuracy_metrics.csv
```

### Quy Tắc Bất Biến (Invariant Rules):
1. **Tuyệt đối không xả nén ảnh ra `/kaggle/working`:** Mọi hình ảnh phải được đọc dưới dạng binary stream từ `cached_keyframes.blob` thông qua `io.BytesIO`.
2. **Mount Dataset cố định:** File `.blob` được quản trị trên Kaggle Dataset (`nhathoang42/aic2025-keyframes-blob`) và được mount ở chế độ Read-Only tại `/kaggle/input`.
3. **Phân vùng Output sạch:** Thư mục `/kaggle/working` chỉ được phép lưu trữ file chỉ mục vector `.faiss`, file báo cáo Markdown và file metrics JSON.

---

## 4. Checklist Thao Tác Chuẩn Khi Khởi Chạy Trên Kaggle

- [ ] **Bước 1 (Session Options):** Chọn Accelerator là `GPU T4 x2` (cho Benchmark) hoặc `TPU v5e` (cho Mass Extraction).
- [ ] **Bước 2 (Mạng):** Bật `Internet on` trong Session Options để tải trọng số mô hình.
- [ ] **Bước 3 (Dữ liệu vào):** Bấm `+ Add Input` $\to$ Thêm `nhathoang42/aic2025-keyframes-blob`.
- [ ] **Bước 4 (Cấu hình Debug):**
  - Chạy thử `DEBUG_MODE = True` (10 mẫu) để xác thực toàn bộ module nạp không bị lỗi VRAM.
  - Chuyển `DEBUG_MODE = False` (1000 mẫu) để chạy đo đạc chính thức.
- [ ] **Bước 5 (Thu hoạch):** Tải các file `.md`, `.json`, `.csv` từ mục Output về thư mục `data/results/` cục bộ.
