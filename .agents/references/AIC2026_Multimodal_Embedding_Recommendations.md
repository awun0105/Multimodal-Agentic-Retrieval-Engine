# Đề xuất mô hình Multimodal Embedding cho AIC 2026 Video Retrieval

## Bối cảnh

Pipeline benchmark hiện tại:

-   CLIP ViT-B
-   SigLIP Base
-   SigLIP So400m
-   Jina CLIP v2
-   ViCLIP-OT

Mục tiêu: Text (Tiếng Việt hoặc dịch sang tiếng Anh) → Keyframe
Retrieval bằng FAISS trên Google Colab T4 (16GB).

## Đề xuất 3 mô hình Multilingual

### 1. Qwen3-VL-Embedding-2B

**Lý do** - Thuộc nhóm SOTA open-source cuối 2025--2026 cho multimodal
retrieval. - Hiểu ngữ nghĩa đa ngôn ngữ rất mạnh, trong đó có tiếng
Việt. - OCR và câu truy vấn dài tốt.

**Ưu điểm** - Multilingual mạnh. - Retrieval vượt Jina CLIP v2 trên
nhiều benchmark mới. - Semantic alignment tốt.

**Nhược điểm** - 2B tham số. - Encode chậm hơn khoảng 3--5 lần. - Index
lâu hơn.

**VRAM** - FP16: \~8--10 GB - INT4: \~5 GB

**HF** - AutoProcessor - AutoModel

------------------------------------------------------------------------

### 2. VLM2Vec-V2

**Ưu điểm** - Được huấn luyện trực tiếp cho embedding. - Mạnh cho
image/video retrieval. - OCR và semantic retrieval tốt.

**Nhược điểm** - Chưa phổ biến. - Một số checkpoint cần
`trust_remote_code=True`.

**VRAM** - Khoảng 7--12 GB

**HF** - Đa số dùng AutoModel.

------------------------------------------------------------------------

### 3. EVA-CLIP

**Ưu điểm** - Rất mạnh nếu truy vấn đã dịch sang tiếng Anh. - Object
retrieval và scene retrieval xuất sắc. - Nhanh, ổn định.

**Nhược điểm** - Không mạnh cho tiếng Việt trực tiếp.

**VRAM** - Base: \~3 GB - Large: \~6--8 GB

**HF** - AutoModel.

------------------------------------------------------------------------

## Đề xuất 2 mô hình tiếng Anh

### 1. DFN CLIP

**Ưu điểm** - English retrieval rất mạnh. - Tốc độ gần tương đương Jina.

**Nhược điểm** - Không hỗ trợ multilingual tốt.

**VRAM** - 4--7 GB

------------------------------------------------------------------------

### 2. MetaCLIP-2

**Ưu điểm** - Train trên dữ liệu cực lớn. - Retrieval tiếng Anh rất
mạnh. - Tích hợp đơn giản.

**Nhược điểm** - Không phù hợp truy vấn tiếng Việt trực tiếp.

**VRAM** - 4--8 GB

------------------------------------------------------------------------

# So sánh với Jina CLIP v2

  ---------------------------------------------------------------------------------------------------------------
  Model                   VN           Multilingual      Retrieval     Tốc độ       VRAM      HF
  ----------------------- ------------ ----------------- ------------- ------------ --------- -------------------
  Jina CLIP v2            ⭐⭐⭐⭐⭐   ⭐⭐⭐⭐⭐        ⭐⭐⭐⭐⭐    ⭐⭐⭐⭐⭐   4--5GB    AutoModel

  Qwen3-VL-Embedding-2B   ⭐⭐⭐⭐⭐   ⭐⭐⭐⭐⭐        ⭐⭐⭐⭐⭐+   ⭐⭐         8--10GB   AutoModel

  VLM2Vec-V2              ⭐⭐⭐⭐☆    ⭐⭐⭐⭐☆         ⭐⭐⭐⭐⭐+   ⭐⭐         7--12GB   AutoModel /
                                                                                              trust_remote_code

  EVA-CLIP                ⭐⭐         ⭐⭐              ⭐⭐⭐⭐⭐    ⭐⭐⭐⭐☆    3--8GB    AutoModel

  DFN CLIP                ⭐⭐         ⭐⭐              ⭐⭐⭐⭐⭐    ⭐⭐⭐⭐⭐   4--7GB    AutoModel

  MetaCLIP-2              ⭐⭐         ⭐⭐              ⭐⭐⭐⭐⭐    ⭐⭐⭐⭐⭐   4--8GB    AutoModel
  ---------------------------------------------------------------------------------------------------------------

------------------------------------------------------------------------

# Khuyến nghị benchmark trên Colab T4

## Multilingual

1.  Jina CLIP v2
2.  Qwen3-VL-Embedding-2B
3.  VLM2Vec-V2

## English

1.  EVA-CLIP
2.  DFN CLIP
3.  MetaCLIP-2

## Ensemble

Khuyến nghị thử: - Reciprocal Rank Fusion (RRF) - Weighted score fusion

giữa: - Jina CLIP v2 - Qwen3-VL-Embedding-2B

để cải thiện Recall@100 và Recall@1000.

## Kết luận

Nếu chỉ được chọn thêm **3 mô hình**:

1.  Qwen3-VL-Embedding-2B
2.  VLM2Vec-V2
3.  EVA-CLIP

Nếu benchmark thêm **2 mô hình tiếng Anh**:

1.  DFN CLIP
2.  MetaCLIP-2

Đây là nhóm mô hình đáng thử nhất cho bài toán AIC Video Retrieval 2026
với pipeline embedding + FAISS trên Google Colab T4.
