# Thư mục Nghiên cứu & Thực nghiệm: OCR & ASR Tiếng Việt

Thư mục này chứa toàn bộ các nghiên cứu, đánh giá so sánh hiệu năng của nhiều mô hình OCR (Nhận dạng chữ viết) và ASR (Nhận dạng giọng nói) Tiếng Việt trên GPU, cùng các script tiện ích tích hợp dùng cho production.

---

## 1. Cấu Trúc Thư Mục `research/ocr_asr`

Các đường dẫn của toàn bộ dự án đã được chuẩn hóa thành đường dẫn tương đối:

```text
research/ocr_asr/
├── data/                       # Dữ liệu mẫu đầu vào (Đã được copy đồng bộ)
│   ├── frame/                  # Keyframe trích xuất từ video cho OCR
│   │   └── L02_V016/           # Tập keyframe .webp mẫu
│   └── audio/                  # Âm thanh .wav mẫu (16,000 Hz, mono) cho ASR
├── ocr/                        # Phân tích & So sánh OCR
│   ├── ocr_comparison.ipynb    # Notebook so sánh 5 pipeline OCR trên GPU
│   ├── ocr_comparison_results.json # Dữ liệu đầu ra nhận diện của 5 pipeline OCR
│   └── ocr_evaluation_summary.md   # Bảng phân tích chi tiết ưu/nhược điểm các model OCR
├── asr/                        # Phân tích & So sánh ASR
│   ├── asr_comparison.ipynb    # Notebook so sánh 5 cấu hình ASR trên GPU
│   ├── run_asr_comparison.py   # Script tự động chạy và đo thời gian chạy của cả 5 cấu hình ASR
│   ├── asr_comparison_results.json # Dữ liệu đầu ra dạng phân đoạn kèm start_time/end_time
│   └── asr_evaluation_summary.md   # Bảng phân tích chi tiết hiệu năng và tiêu chí quy mô lớn (200k samples)
├── main.py                     # Script tiện ích chính chạy CLI (EasyOCR + NeMo)
└── ocr_asr_utils.py            # Bản sao tiện ích hỗ trợ import nhanh vào project lớn
```

---

## 2. Hướng Dẫn Tự Kiểm Thử (Verification Guide)

Bạn có thể tự chạy kiểm thử (verify) chức năng của mô hình OCR và ASR trực tiếp bằng dòng lệnh từ thư mục gốc của repository (`Multimodal-Agentic-Retrieval-Engine`):

### Kiểm thử OCR (Sử dụng EasyOCR)
Lệnh này sẽ nhận diện văn bản trên một keyframe webp mẫu:
```bash
uv run research/ocr_asr/main.py --mode ocr --input research/ocr_asr/data/frame/L02_V016/keyframe_10056.webp
```
*Kết quả kỳ vọng:* Đầu ra in ra các bounding box tọa độ, độ tin cậy và văn bản được giải mã chính xác (ví dụ: `"Ông ĐÔ TÂN LONG"`, `"Pho GiaM ĐỖC TT Ha TÃNG..."`).

### Kiểm thử ASR (Sử dụng NVIDIA NeMo parakeet-ctc-0.6b-vi)
Lệnh này sẽ nhận dạng giọng nói trên file âm thanh wav 16kHz mẫu:
```bash
uv run research/ocr_asr/main.py --mode asr --input research/ocr_asr/data/audio/1yHly8dYhIQ.wav
```
> Lưu ý: Đôi khi phải cài thêm ffmmpeg

*Kết quả kỳ vọng:* Chương trình chia file âm thanh thành các chunk 30s và in ra các câu nhận diện tiếng Việt hoàn chỉnh kèm mốc thời gian bắt đầu/kết thúc (ví dụ: `[0.00s - 30.00s]: "K kính chào quý vị, rất hân hạnh..."`).

---

## 3. Các Thử Nghiệm OCR Đã Thực Hiện

Các thử nghiệm so sánh hiệu năng được thực hiện trên 5 cấu hình pipeline khác nhau:
1. **PaddleOCR + VietOCR**: Phát hiện vùng chữ bằng Paddle và giải mã bằng VietOCR (vgg_seq2seq).
2. **PaddleOCR Only**: Sử dụng mô hình PP-OCRv5 end-to-end (Nhanh nhất, khoảng ~0.038s/ảnh).
3. **EasyOCR**: Hỗ trợ tiếng Việt rất tốt, giữ dấu chuẩn xác nhất (Tốt nhất cho Tiếng Việt, khoảng ~0.060s/ảnh).
4. **PaddleOCR + TrOCR**: Dùng TrOCR để giải mã hộp chữ (Model gốc tiếng Anh, không tối ưu cho tiếng Việt).
5. **Florence-2**: Vision-Language Model của Microsoft chạy autoregressive trên GPU (Độ trễ cao ~2.6s/ảnh và không tối ưu cho tiếng Việt).

Chi tiết báo cáo và bảng kết quả có thể được xem tại [ocr_evaluation_summary.md](./ocr/ocr_evaluation_summary.md).

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

## 5. Cách Cài Đặt Dependencies

Để chạy thành công, môi trường của dự án cần cài đặt các thư viện sau:

```bash
# 1. Cài đặt PyTorch CUDA tương thích với GPU
uv add torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# 2. Cài đặt các package xử lý OCR & ASR
uv add easyocr nemo-toolkit[asr] soundfile librosa
```

---

## 6. Hướng dẫn Tải và Chuẩn bị Dữ liệu (Data Download & Setup)

*Phần này dành cho bạn tự cập nhật phương pháp tải/chuẩn bị bộ dữ liệu quy mô lớn (ví dụ: script tải từ YouTube, link Drive chứa dữ liệu frame, cấu trúc convert sang WebP/WAV 16kHz, v.v.):*

# Link Data

Vào link này tải folder data về để ở trong folder `research/ocr_asr/data/` nhé 

[Data GGDrive](https://drive.google.com/drive/folders/1VYWu18eFBpcVJ87yA-RDACSmtA2AJWpy?usp=sharing)
