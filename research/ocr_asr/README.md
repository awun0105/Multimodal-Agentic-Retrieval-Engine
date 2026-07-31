# Dự án Thử Nghiệm OCR & ASR

Kho lưu trữ mã nguồn và các tài liệu thử nghiệm cho hai tác vụ:
1. **OCR (Optical Character Recognition)**: Nhận diện văn bản từ hình ảnh (keyframes trích xuất từ video).
2. **ASR (Automatic Speech Recognition)**: Nhận diện giọng nói từ âm thanh (trích xuất từ video).

---

## 1. Cấu Trúc Thư Mục Dự Án

Dự án được tổ chức gọn gàng để tách biệt dữ liệu lớn và mã nguồn thử nghiệm:

```text
├── data/                       # Thư mục dữ liệu chứa hình ảnh/âm thanh (Bị Git ignore)
│   ├── frame/                  # Các keyframe trích xuất từ video làm dữ liệu đầu vào cho OCR
│   ├── video/                  # Video gốc dạng .mp4 tải từ YouTube
│   └── audio/                  # Âm thanh dạng .wav được trích xuất (16,000 Hz, mono)
├── ocr/                        # Thư mục chứa toàn bộ mã nguồn và thực nghiệm OCR
│   ├── ocr.ipynb               # Notebook chạy baseline (PaddleOCR + VietOCR)
│   ├── ocr_comparison.ipynb    # Notebook so sánh 5 pipeline OCR trên GPU
│   ├── OCR.json                # Kết quả trích xuất văn bản từ baseline
│   ├── ocr_comparison_results.json # Kết quả dạng JSON lưu thông tin nhận diện & thời gian chạy của 5 pipeline
│   ├── ocr_evaluation_summary.md   # Bảng nhận xét, so sánh chi tiết hiệu năng/độ chính xác của 5 pipeline
│   └── visualize/              # Ảnh kết quả vẽ khung chữ và nhận diện (Bị Git ignore)
├── asr/                        # Thư mục chứa toàn bộ mã nguồn và thực nghiệm ASR
│   ├── asr_comparison.ipynb    # Notebook so sánh 5 cấu hình ASR trên GPU
│   ├── run_asr_comparison.py   # Runner script chạy thử nghiệm ASR tự động
│   ├── asr_comparison_results.json # Kết quả trích xuất dạng JSON kèm start_time và end_time của 5 cấu hình
│   └── asr_evaluation_summary.md   # Bảng báo cáo phân tích, so sánh hiệu năng và chất lượng của 5 cấu hình ASR
├── main.py                     # File chạy chính của chương trình (Boilerplate)
├── pyproject.toml              # Định nghĩa các package phụ thuộc (Pillow, EasyOCR, Transformers, PyTorch GPU...)
├── README.md                   # Tài liệu hướng dẫn sử dụng này
└── uv.lock                     # Lockfile của bộ quản lý thư viện UV
```

---

## 2. Hướng Dẫn Cài Đặt Môi Trường

Dự án sử dụng bộ quản lý package **UV** và được cấu hình để tận dụng tối đa phần cứng **NVIDIA GPU** thông qua CUDA 12.4.

### Bước 1: Khởi tạo virtual environment và cài đặt thư viện
Chạy lệnh sau tại thư mục gốc của dự án để UV tự động tạo môi trường ảo `.venv` và tải các bản build CUDA của PyTorch/PaddlePaddle:
```bash
uv sync
```

### Bước 2: Kiểm tra thiết bị GPU
Bạn có thể mở Python trong môi trường ảo và kiểm tra xem PyTorch/Paddle đã nhận diện được GPU chưa:
```python
import torch
import paddle
print("PyTorch GPU Available:", torch.cuda.is_available())
print("Paddle GPU Available:", paddle.is_compiled_with_cuda())
```

---

## 3. Các Thử Nghiệm OCR Đã Thực Hiện

Các thử nghiệm so sánh hiệu năng được thực hiện trên các cấu hình pipeline khác nhau:
1. **PaddleOCR + VietOCR**: Phát hiện vùng chữ bằng Paddle và giải mã bằng VietOCR (vgg_seq2seq).
2. **PaddleOCR Only**: Sử dụng mô hình PP-OCRv5 end-to-end (Nhanh nhất, khoảng ~0.038s/ảnh).
3. **EasyOCR**: Hỗ trợ tiếng Việt rất tốt, giữ dấu chuẩn xác nhất (Tốt nhất cho Tiếng Việt, khoảng ~0.060s/ảnh).
4. **PaddleOCR + TrOCR**: Dùng TrOCR để giải mã hộp chữ (Model gốc tiếng Anh, không tối ưu cho tiếng Việt).
5. **Florence-2**: Vision-Language Model của Microsoft chạy autoregressive trên GPU (Độ trễ cao ~2.6s/ảnh và không tối ưu cho tiếng Việt).
6. **Vintern-1B-v3_5 (Mới - SOTA)**: Vision-Language Model chuyên biệt cho tiếng Việt, có độ chính xác Word Error Rate (WER) tốt nhất hiện tại (~0.34), độ trễ ~0.69s/ảnh trên GPU RTX 4060.
7. **Qwen2-VL-2B-Instruct (Mới)**: Vision-Language Model đa ngôn ngữ mạnh mẽ của Alibaba, độ trễ ~1.25s/ảnh nhưng thỉnh thoảng gặp lỗi từ chối trả lời (refusal) bằng tiếng Việt.

Chi tiết báo cáo và bảng kết quả của 5 pipeline ban đầu có tại [ocr_evaluation_summary.md](./ocr/ocr_evaluation_summary.md). 
Thử nghiệm mới nhất về các mô hình VLM được lưu và chạy trực quan tại notebook [ocr_colab_benchmark.ipynb](./ocr/ocr_colab_benchmark.ipynb) và kết quả lưu tại [colab_benchmark_results.json](./ocr/colab_benchmark_results.json).

---

## 4. Các Thử Nghiệm ASR Đã Thực Hiện

Chúng ta thực hiện so sánh hiệu năng nhận diện giọng nói tiếng Việt giữa 5 cấu hình chạy trên GPU:
1. **faster-whisper-medium**: Chạy trên CTranslate2 FP16, nhận diện chất lượng cao kèm dấu câu tự nhiên.
2. **wav2vec 2.0**: Giải mã CTC thô bằng PyTorch, chạy cực nhanh (~198x) nhưng văn bản không có viết hoa, dấu câu.
3. **faster-whisper-large-v3 (INT8)**: Chạy model 1.5B qua lượng tử hóa INT8 GPU tối ưu hóa tốc độ gấp 2x và tiết kiệm VRAM.
4. **Wav2Vec 2.0 + Punctuation**: Kết hợp Wav2Vec2 và model `vibert-capu` cục bộ để khôi phục viết hoa và dấu câu.
5. **NVIDIA FastConformer**: Chạy NeMo `parakeet-ctc-0.6b-vi` trên GPU, tốc độ nhanh nhất (~268x) và tự động hỗ trợ dấu câu/viết hoa natively.

Chi tiết báo cáo và bảng kết quả so sánh có thể được xem tại [asr_evaluation_summary.md](./asr/asr_evaluation_summary.md).

---

## 5. Hướng Dẫn Tải Lại Trọng Số Mô Hình (Model Weights Download Guide)

Để giữ cho repository gọn nhẹ, toàn bộ trọng số mô hình cồng kềnh (binary weights) đã được xóa bỏ khỏi thư mục dự án và thêm vào quy tắc Git loại trừ. Khi bạn chạy lại các thử nghiệm hoặc script production, các mô hình sẽ được xử lý như sau:

### 1. Các mô hình tự động tải (Auto-download)
Hầu hết các mô hình sẽ tự động được tải xuống từ Hugging Face Hub hoặc máy chủ tương ứng trong lần chạy đầu tiên:
- **EasyOCR**: Tự động tải trọng số tiếng Việt & Anh về thư mục `~/.EasyOCR/model/`.
- **NVIDIA FastConformer**: Tự động tải checkpoint từ NeMo Hub về thư mục `~/.cache/torch/NeMo/`.
- **faster-whisper (medium / large-v3)**: Tự động tải về cache Hugging Face (`~/.cache/huggingface/hub/`).
- **wav2vec 2.0 (`khanhld/...`)**: Tự động tải về cache Hugging Face thông qua thư viện `transformers`.

### 2. Mô hình cần tải thủ công và vá lỗi (`vibert-capu` cho ASR Punctuation)
Để chạy lại thử nghiệm số 4 (**Wav2Vec 2.0 + Punctuation**), bạn cần chuẩn bị lại mô hình khôi phục dấu câu `vibert-capu` như sau:
1. Tạo lại thư mục: `asr/capu/`.
2. Truy cập [dragonSwing/vibert-capu](https://huggingface.co/dragonSwing/vibert-capu) trên Hugging Face.
3. Tải toàn bộ các file cấu hình và file trọng số lớn `pytorch_model.bin` bỏ vào thư mục `asr/capu/`.
4. Để khắc phục lỗi không tương thích với PyTorch/Transformers mới, hãy mở file `asr/capu/modeling_seq2labels.py` và sửa 2 lỗi sau:
   - Thêm decorator `@dataclass` ngay trước class `Seq2LabelsOutput` (khoảng dòng 17).
   - Truyền thêm `mean_resizing=False` vào lời gọi phương thức `resize_token_embeddings` (khoảng dòng 50).

# Link Data

Vào link này tải folder data về để ở trong folder `research/ocr_asr/data/` nhé 

[Data GGDrive](https://drive.google.com/drive/folders/1VYWu18eFBpcVJ87yA-RDACSmtA2AJWpy?usp=sharing)
