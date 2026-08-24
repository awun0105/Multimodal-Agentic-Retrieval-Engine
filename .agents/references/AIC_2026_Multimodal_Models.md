# Gợi ý và So sánh Mô hình Multimodal SOTA cho Cuộc thi AIC 2026 (Video Retrieval)

**Môi trường:** Google Colab (GPU T4 - 15GB VRAM khả dụng)
**Mục tiêu:** Truy xuất Video Keyframes bằng văn bản Tiếng Việt / Tiếng Anh.

Tính đến năm 2026, kiến trúc Vision-Language đã có nhiều bước tiến lớn, đặc biệt là sự trỗi dậy của **Mạng tương tác trễ (Late Interaction)** và **Loss Sigmoid đa ngôn ngữ**. Với GPU T4, bạn hoàn toàn chạy mượt các model kích thước ViT-Large (chỉ chiếm ~1.5 - 2GB VRAM ở chuẩn FP16) với batch_size lớn.

Dưới đây là danh sách các mô hình Multimodal Embedding tối ưu nhất để đưa vào Pipeline benchmark, so sánh trực tiếp với **Jina CLIP v2**.

---

## Top 3 Mô hình Đa ngôn ngữ / Hỗ trợ Tiếng Việt xuất sắc nhất
Thay vì tốn chi phí và độ trễ cho API dịch thuật, các mô hình này hiểu trực tiếp truy vấn Tiếng Việt với độ sâu ngữ nghĩa cao:

### 1. Google SigLIP 2 (Bản Multilingual)
Bản nâng cấp toàn diện của SigLIP với *self-distillation*, *masked prediction*, và hàm loss Sigmoid độc quyền.
* **So sánh với Jina CLIP v2:** Hỗ trợ native 109 ngôn ngữ (bao gồm Tiếng Việt cực tốt). Vượt trội Jina CLIP v2 ở khả năng nhận diện vật thể nhỏ (fine-grained localization) trong frame. Jina thiên về context text dài, còn SigLIP 2 tối ưu thuần túy cho hình ảnh.
* **VRAM & Tốc độ:** ~1.7GB VRAM (bản ViT-L/14). Tốc độ (fps) tương đương Jina CLIP v2.
* **Độ tương thích HF:** Tương thích native 100% trong `transformers >= 4.50` (chỉ cần dùng `AutoModel`).

### 2. ColPali / ColCLIP (Kiến trúc Multi-vector / MaxSim)
Chia ảnh thành các patch và tạo ra **ma trận vector** thay vì 1 vector duy nhất. Truy vấn sử dụng thuật toán MaxSim đối chiếu từng từ trong text với từng vùng trong ảnh.
* **So sánh với Jina CLIP v2:** Độ chính xác (Accuracy) cho tìm kiếm chi tiết nhỏ bỏ xa Jina CLIP v2. Đặc biệt hữu dụng nếu query của AIC cực kỳ chi tiết.
* **VRAM & Tốc độ:** Load model tốn ~3GB (PaliGemma backbone). **Nhược điểm:** Cần dung lượng RAM/Ổ cứng khổng lồ để lưu trữ Vector Index (gấp ~100 lần CLIP thường) và tốc độ search chậm hơn.
* **Độ tương thích HF:** Không thể dùng `AutoModel` truyền thống (phải dùng pipeline thư viện `colpali-engine`).

### 3. M-CLIP (XLM-Roberta-Large-ViT-L-14) / BGE-Visualized
Sự kết hợp giữa Text Encoder cực mạnh (XLM-R) và Vision Encoder.
* **So sánh với Jina CLIP v2:** Hiểu Tiếng Việt tự nhiên và tiếng lóng tốt hơn do Text Encoder được train riêng rẽ trên kho văn bản đa ngôn ngữ khổng lồ.
* **VRAM & Tốc độ:** ~1.8GB VRAM. Tốc độ inference cực nhanh.
* **Độ tương thích HF:** Dễ dàng tích hợp qua thư viện `sentence-transformers` hoặc `open_clip`.

---

## Top 2 Mô hình Tiếng Anh cực mạnh (Nên dùng kèm API dịch)
Nếu hệ thống cho phép dịch query Tiếng Việt sang Tiếng Anh, hai "quái vật" này mang lại lợi thế vượt trội:

### 1. EVA-02-CLIP (ViT-L/14 hoặc ViT-E)
Phát triển bởi BAAI, học được các biểu diễn cực kỳ "dày đặc" (dense) và chi tiết.
* **So sánh với Jina CLIP v2:** Cấu trúc Transformer tối ưu hơn cho hình ảnh. Jina thắng ở Text dài, nhưng EVA-02 thắng tuyệt đối ở khả năng bóc tách hình ảnh phức tạp.
* **VRAM & Tốc độ:** Bản ViT-L/14 chiếm ~1.3GB VRAM, chạy batch size 128 trên T4 nhẹ nhàng.
* **Độ tương thích HF:** Có sẵn trên hub của BAAI, dùng `timm` hoặc `transformers` đều được.

### 2. Apple DFN5B-CLIP (Data Filtering Network)
Train trên 5 tỷ cặp ảnh-text được lọc sạch nhiễu bằng thuật toán khắt khe.
* **So sánh với Jina CLIP v2:** Tính "Robustness" (độ kháng nhiễu) cao hơn hẳn. Chuyên trị các keyframes mờ, chuyển động nhanh hoặc góc cắt xấu trong video retrieval.
* **VRAM & Tốc độ:** Rất tối ưu, tương đương các dòng ViT-Large khác.
* **Độ tương thích HF:** Hỗ trợ sẵn trong hệ sinh thái `open_clip`.

---

## Lời khuyên chiến thuật cho AIC 2026
* **Tối đa hóa độ chính xác:** Nếu bạn có dư dả tài nguyên ổ cứng/RAM để lưu vector, hãy thử ngay **ColPali / ColCLIP**. Khả năng đối chiếu MaxSim biến bài toán "tìm kiếm frame" thành "tìm kiếm vật thể trong frame", đẩy điểm MAP lên rất cao.
* **Tối ưu hóa tài nguyên & tốc độ:** Nếu ưu tiên pipeline gọn nhẹ (Single-vector / Bi-encoder) cho T4 mà vẫn muốn hỗ trợ Tiếng Việt native, thì **SigLIP 2 (Multilingual)** là sự lựa chọn số 1.
