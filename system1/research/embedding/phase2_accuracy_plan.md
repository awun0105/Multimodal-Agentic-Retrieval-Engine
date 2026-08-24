# Kế Hoạch Phase 2: Đánh Giá Độ Chính Xác (Accuracy Benchmark)
**Thời gian cập nhật:** Tháng 8/2026
**Mục tiêu cốt lõi:** Xác định mô hình Nhúng (Embedding) tốt nhất cho hệ thống AIC 2026 dựa trên chất lượng trích xuất đặc trưng (Retrieval Accuracy), sau khi đã qua vòng loại Tốc độ (Speed) ở Phase 1.

---

## 1. Bài Toán Lõi (The Core Dilemma)
Hệ thống đối mặt với 2 trường phái kiến trúc:
1. **Dịch thuật (Translate-then-Search):** Dùng API/Mô hình dịch câu truy vấn Tiếng Việt sang Tiếng Anh, sau đó băm (embed) bằng các siêu mô hình Tiếng Anh hiện đại nhất.
2. **Trực tiếp (Native Zero-shot):** Dùng thẳng mô hình có khả năng hiểu đa ngôn ngữ (Multilingual) để băm trực tiếp câu Tiếng Việt.

**Nhiệm vụ của Phase 2:** Dùng số liệu (Data-driven) để dứt điểm bài toán này.

---

## 2. Kinh Nghiệm Kế Thừa Từ Phase 1
Để đảm bảo Phase 2 diễn ra trơn tru, ta **bắt buộc duy trì** các bài học xương máu từ Phase 1:
- **Xử lý I/O Bottleneck:** Giữ nguyên kiến trúc *Virtual Cache Reader (`.blob`)*. Độ chính xác yêu cầu load rất nhiều ảnh chất lượng cao để vector hóa, việc đọc trực tiếp qua memory-mapping (chunking) trên Kaggle/Colab là sống còn để không bị lỗi Disk Quota (20GB).
- **Hệ quy chiếu phần cứng:** Duy trì chạy song song kịch bản trên Kaggle (Dual T4) làm máy chủ chính, và Google Colab (Single T4 / L4) làm fallback.
- **Tính module hóa:** Sử dụng lại lõi `extractor.py` (với hàm `get_vector` chuẩn hóa L2 norm) để đảm bảo vector sinh ra ở Phase 2 khớp hoàn toàn với định dạng đo lường.

---

## 3. Danh Sách 14 Mô Hình Tham Gia Vòng 2 (Candidate Matrix)

| 1. Thuần Tiếng Việt (Dedicated) | 2. Multilingual-CLIP (M-CLIP) | 3. Đa Ngôn Ngữ SOTA (Global) | 4. Dịch Thuật Đối Chiếu (English) |
| :--- | :--- | :--- | :--- |
| `minhnguyent546/ViCLIP-OT` (512d) | `M-CLIP/XLM-Roberta-Large-Vit-B-32` (512d) | `sentence-transformers/clip-ViT-B-32-multilingual-v1` (512d) | `google/siglip-base-patch16-224` (768d) |
| `minhnguyent546/ViSigLIP-OT` (768d) | `M-CLIP/XLM-Roberta-Large-Vit-L-14` (768d) | `BAAI/AltCLIP` (768d - Distilled XLM-R) | `openai/clip-vit-base-patch32` (512d) |
| | | `open_clip:ViT-B-16-SigLIP-i18n-256:webli` (768d) | `facebook/metaclip-b32-400m` (512d) |
| | | `open_clip:ViT-L-16-SigLIP-256:webli` (1024d) | `apple/DFN2B-CLIP-ViT-B-16` (512d) |
| | | `jinaai/jina-clip-v1` (768d - 8k Context) | `open_clip:convnext_base_w:laion...` (640d) |
| | | `open_clip:xlm-roberta-base-ViT-B-32:laion5b...` (512d) | |

*(Đã loại bỏ toàn bộ các mô hình Huge/Giant >100s/1000 ảnh từ Phase 1 để tối ưu tài nguyên).*

---

## 4. Giao Thức Đánh Giá (Evaluation Protocol)

### A. Xây dựng Tập dữ liệu Ground Truth
- **Quy mô:** 500 - 1000 ảnh (được trích xuất từ các video AIC).
- **Quy tắc phân bổ 90/10 (Sampling Strategy):**
  - **90% đoạn giữa ($t \in [60\text{s}, T - 60\text{s}]$):** Tập trung vào nội dung sự kiện, hành động và con người thực tế, loại bỏ nhiễu intro/credits.
  - **10% đoạn biên ($t \in [0, 60\text{s}]$ hoặc $[T - 60\text{s}, T]$):** Thử thách khả năng kháng nhiễu đối với logo đài truyền hình, animation và intro.
  - Được tự động hóa qua module [`ground_truth_sampler.py`](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/Multimodal-Agentic-Retrieval-Engine/system1/research/embedding/benchmark_testing/prep/ground_truth_sampler.py).
- **Nguồn nhãn (Annotation Source):**
  1. *Đề thi KIS chính thức AIC 2023 - 2025:* Chuẩn mực phong cách ra đề của BTC.
  2. *VLM Pipeline (Qwen2.5-VL / Gemini Flash):* Sinh cặp mô tả chi tiết: 1 câu Tiếng Việt (chủ thể, hành động, màu sắc, vị trí không gian) và 1 câu Tiếng Anh dịch chuẩn.
  3. *Human Review:* Tinh chỉnh và loại bỏ các câu miêu tả chung chung.

### B. Chỉ số Đo lường (Metrics & Rationale)
Output của Phase 2 sinh ra 2 bảng ma trận (Query Tiếng Anh vs Query Tiếng Việt) với các thông số:
1. **Recall@1, Recall@5, Recall@10:** Đo lường tỷ lệ ảnh đúng xuất hiện trong Top K kết quả (phù hợp với trang đầu hiển thị của Web UI thi đấu).
2. **MRR (Mean Reciprocal Rank):** Đánh giá thứ hạng ưu tiên, thưởng điểm cao khi đáp án đúng xuất hiện ở vị trí đầu.
3. **Cosine Margin ($S_{\text{pos}} - \max_{j \ne i} S_{ij}$):** Độ phân tách giữa ảnh đúng và ảnh sai gần nhất (Hard Negative) để ngăn chặn hiện tượng hallucination / false positive.

### C. Quá trình Vận hành (Execution Pipeline)
1. **Virtual Cache Reader:** Nạp 1.000 keyframes từ tệp `.blob` vào VRAM GPU.
2. **Đo đạc tự động:** Chạy kịch bản [`accuracy_benchmark.py`](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/Multimodal-Agentic-Retrieval-Engine/system1/research/embedding/benchmark_testing/phase_2/accuracy_benchmark.py) (hoặc Notebook [`accuracy_benchmark.ipynb`](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/Multimodal-Agentic-Retrieval-Engine/system1/research/embedding/benchmark_testing/phase_2/accuracy_benchmark.ipynb)).
3. **Tổng hợp:** Xuất báo cáo markdown `phase2_accuracy_report.md` và tệp metrics JSON/CSV tại thư mục `data/results/`.

