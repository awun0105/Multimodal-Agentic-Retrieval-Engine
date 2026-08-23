# BẢN CHIA VIỆC NGHIÊN CỨU VÀ THỰC NGHIỆM MÔ HÌNH MULTIMODAL
**Phân công cho 3 người phụ trách 3 mảng:** Embedding, OCR & ASR, VLM & Prompting

---

## I. Mục tiêu chung
- Nhóm cần nghiên cứu, thực nghiệm và lựa chọn các mô hình tối ưu từ hệ sinh thái **Hugging Face** để phục vụ bài toán xử lý dữ liệu đa phương thức (Ảnh, Text, Âm thanh, Video frame).
- Mỗi người phụ trách một mảng độc lập, nhưng kết quả cuối cùng phải có khả năng tích hợp vào hệ thống lõi.
- Toàn bộ mã nguồn và báo cáo phải được nộp thông qua **Pull Request trên nhánh `research-branch`**.

---

## II. Phân công công việc chi tiết

### 1. Người 1: Mảng Embedding (Vector hóa Ảnh & Text)
* **Mục tiêu:** 
  - Chuyển đổi ảnh và text thành vector trong cùng một không gian embedding để so sánh độ tương đồng ngữ nghĩa giữa ảnh và câu mô tả.
  - Đảm bảo độ chính xác để không làm sai lệch việc đối chiếu vector, tránh ảnh hưởng đến chất lượng tìm kiếm.
* **Công việc cần làm:**
  - Tìm kiếm mô hình trên Hugging Face thuộc nhóm `feature-extraction`, `sentence-similarity` hoặc hỗ trợ đa phương thức.
  - Lọc ra ít nhất 3 mô hình ứng viên (VD: **SigLIP, BGE Visual, Jina CLIP** hoặc các biến thể CLIP mới hơn).
  - Xây dựng script/notebook benchmark trên Google Colab trên cùng tập dữ liệu mẫu.
  - Đánh giá theo các chỉ số: *Latency, Recall@K, Cosine Similarity, VRAM tiêu thụ, khả năng xử lý batch*.
  - Chọn 1 mô hình tốt nhất.
* **Hàm Python cần hoàn thiện:**
  ```python
  def get_vector(input_data):
      """
      Nhận đầu vào là ảnh hoặc text.
      Trả về vector embedding tương ứng.
      """
      pass
  ```
* **Sản phẩm bàn giao:**
  - File mã nguồn chứa hàm `get_vector(input_data)` chạy ổn định.
  - Notebook/script Colab benchmark.
  - File `report.md` (danh sách 3 mô hình, bảng so sánh, lý do chọn, cấu hình thử nghiệm).
  - Pull Request lên nhánh `research-branch`.

---

### 2. Người 2: Mảng OCR & ASR (Trích xuất Text từ Ảnh & Âm thanh)
* **Mục tiêu:**
  - Trích xuất text thô từ ảnh, frame video và âm thanh để bổ sung cho Embedding (nhận diện chữ số, biển báo, text nhỏ, lời thoại).
* **Công việc cần làm:**
  - **OCR:** Thử nghiệm ít nhất 3 mô hình/công cụ (VD: **PaddleOCR, Florence-2, TrOCR, EasyOCR**,...).
  - **ASR:** Thử nghiệm ít nhất 3 mô hình/công cụ (VD: **Whisper, Faster-Whisper, WhisperX**,...).
  - **Tiền xử lý ảnh (OpenCV):** Áp dụng *grayscale, tăng tương phản, thresholding, sharpening, denoising, resize/upscale, morphology* với ảnh mờ/lóa/nhiễu.
  - **Đánh giá:** Theo chỉ số *CER, WER, độ chính xác text/transcript, latency, VRAM/RAM tiêu thụ, độ ổn định với dữ liệu nhiễu*.
  - *Lưu ý:* Đầu ra của ASR **bắt buộc phải kèm Timestamp**.
* **Hàm Python cần hoàn thiện:**
  ```python
  def extract_audio_text(file):
      """
      Nhận đầu vào là file âm thanh hoặc video.
      Trả về text transcript kèm timestamp.
      """
      pass

  def extract_image_text(image):
      """
      Nhận đầu vào là ảnh hoặc frame ảnh.
      Trả về text đã OCR được sau tiền xử lý.
      """
      pass
  ```
* **Sản phẩm bàn giao:**
  - File mã nguồn chứa 2 hàm `extract_audio_text(file)` và `extract_image_text(image)`.
  - Script / Notebook benchmark OCR & ASR.
  - File `report.md` (danh sách 3 mô hình OCR, 3 mô hình ASR, bảng so sánh WER/CER, latency, VRAM/RAM, cấu hình OpenCV tối ưu, lý do chọn).
  - Pull Request lên nhánh `research-branch`.

---

### 3. Người 3: Mảng VLM & Prompting (Sinh Text mô tả & Ép cấu trúc JSON)
* **Mục tiêu:**
  - Sử dụng Vision-Language Model (VLM) nhỏ gọn để phân tích ngữ cảnh ảnh và sinh metadata chuẩn dạng JSON. Bổ sung ngữ cảnh, hành động, đối tượng, màu sắc cho ảnh.
* **Công việc cần làm:**
  - Khảo sát các mô hình VLM nhỏ gọn (**< 7B tham số**) hỗ trợ **lượng tử hóa 4-bit** (VD: **Qwen-VL, PaliGemma, InternVL bản nhỏ, Moondream**,...).
  - Design Prompt chặt chẽ để ép output về đúng 1 cấu trúc JSON tĩnh, không chứa text thừa/giao tiếp.
  - Trường `caption_chi_tiet` phải mô tả đầy đủ ngữ cảnh, đối tượng, hành động, màu sắc, bối cảnh.
  - Thử nghiệm trên ít nhất **100 ảnh mẫu** để kiểm tra: *tỷ lệ JSON hợp lệ, độ chi tiết caption, mức độ tuân thủ prompt, latency, VRAM tiêu thụ, độ ổn định*.
* **Hàm Python cần hoàn thiện & Cấu trúc JSON:**
  ```python
  def generate_json(image):
      """
      Nhận đầu vào là ảnh.
      Trả về JSON mô tả nội dung ảnh theo cấu trúc cố định.
      """
      pass
  ```
  *Cấu trúc JSON mẫu:*
  ```json
  {
    "doi_tuong": ["xe máy", "người"],
    "mau_sac": ["đỏ"],
    "hanh_dong": "đang chạy",
    "boi_canh": "đường ngập nước dưới trời mưa",
    "caption_chi_tiet": "Một người đàn ông mặc áo mưa đỏ đang chạy xe máy qua đoạn đường ngập nước dưới cơn mưa tầm tã."
  }
  ```
* **Sản phẩm bàn giao:**
  - File mã nguồn chứa hàm `generate_json(image)`.
  - File `sample_results.json` thử nghiệm trên 100 ảnh.
  - File `report.md` (danh sách 3 VLM, bảng so sánh latency, VRAM, tỷ lệ JSON hợp lệ, chất lượng caption, prompt tối ưu, lý do chọn).
  - Pull Request lên nhánh `research-branch`.

---

## III. Quy chuẩn Bàn giao & Tiêu chuẩn Hoàn thành

### 1. Quy chuẩn Pull Request (PR)
- Tạo PR lên nhánh `research-branch`.
- Mã nguồn chạy ổn định, hàm rõ ràng, dễ tái sử dụng, không hard-code đường dẫn cá nhân, có xử lý lỗi & comment đầy đủ.
- Đi kèm notebook/script benchmark, file báo cáo `report.md` và kết quả mẫu.

### 2. Yêu cầu cho file `report.md`
Mỗi mảng phải có báo cáo chứa:
- Tên người phụ trách & Mảng phụ trách.
- Mục tiêu thực nghiệm.
- Bảng so sánh ít nhất 3 mô hình với tiêu chí: `Mô hình | Latency | VRAM | Điểm benchmark | Ưu điểm | Nhược điểm | Kết luận`.
- Mô hình được chọn cuối cùng và lý do lựa chọn.
- Cấu hình phần cứng chạy thử nghiệm.
- Các vấn đề gặp phải và giải pháp xử lý.

### 3. Tiêu chí Đánh giá Hoàn thành
Một mảng chỉ được tính là hoàn thành khi:
1. Đã thử nghiệm ít nhất 3 mô hình/công cụ.
2. Có bảng benchmark rõ ràng.
3. Đã chốt mô hình tối ưu cuối cùng.
4. Có hàm Python chạy chuẩn hoạt động được.
5. Có báo cáo `report.md` chi tiết.
6. Đã tạo Pull Request đầy đủ lên nhánh `research-branch`.
7. Kết quả có thể tích hợp trực tiếp vào hệ thống lõi.
