# Cẩm Nang Kiến Trúc Song Song Đa GPU & Phân Tách Mô Hình Đa Phương Thức (Multi-GPU Parallelism & Model Sharding Guide)

Tài liệu này tổng hợp toàn bộ kinh nghiệm thực chiến, phân tích kiến trúc chuyên sâu, các cạm bẫy kỹ thuật (gotchas) và hướng dẫn triển khai tối ưu cho các mô hình Vision-Language (CLIP, SigLIP, AltCLIP, ConvNeXt) trên môi trường Đa GPU (như Kaggle Dual T4, Colab Pro, Server đa card).

---

## 1. Bối Cảnh & Thách Thức Kỹ Thuật

Khi chạy các mô hình truy xuất đa phương tiện (Multimodal Retrieval) trên môi trường 2 GPU (Dual T4):
1. **Giới hạn VRAM & Tràn bộ nhớ (OOM):** Việc đưa toàn bộ tập dữ liệu (1.000+ ảnh) vào GPU cùng lúc trong một hàm forward duy nhất sẽ làm bùng nổ các bản đồ đặc trưng (Feature Maps) và gây lỗi `CUDA Out of Memory`.
2. **Hạn chế của `torch.nn.DataParallel` truyền thống:**
   - **Nghẽn khóa luồng Python (GIL Bottleneck):** Hoạt động theo cơ chế đơn tiến trình - đa luồng, khiến CPU trở thành điểm nghẽn điều phối dữ liệu cho 2 GPU.
   - **Bất đối xứng bộ nhớ (GPU 0 Memory Imbalance):** GPU 0 vừa phải tính toán phần của mình, vừa phải thu gom toàn bộ kết quả từ GPU 1, dẫn đến tiêu tốn gấp đôi VRAM và dễ gây sập OOM.
   - **Xung đột hook nội bộ:** Các mô hình mới (Jina-CLIP, SigLIP) có các lớp tùy biến (RoPE, FlashAttention) không tương thích với cơ chế `scatter/gather` của DataParallel.

---

## 2. So Sánh 4 Trường Phái Phân Tách Mô Hình (Model Parallelism Paradigms)

```
+--------------------------------------------------------------------------------------------------+
| TRƯỜNG PHÁI 1: MODALITY-SPECIFIC TOWER SHARDING (Phân tách theo Tháp Đa phương thức)             |
| [GPU 0: cuda:0] -> Toàn bộ Vision Tower (ViT / ConvNeXt / CNN)                                   |
| [GPU 1: cuda:1] -> Toàn bộ Text Tower (BERT / RoBERTa / Transformer)                             |
| -> Ưu điểm: Giao tiếp qua bus PCIe = 0ms; Không xung đột thư viện; Tối ưu tuyệt đối cho Benchmark.|
+--------------------------------------------------------------------------------------------------+

+--------------------------------------------------------------------------------------------------+
| TRƯỜNG PHÁI 2: PIPELINE PARALLELISM (HuggingFace Accelerate device_map="auto")                   |
| [GPU 0: cuda:0] -> Lớp 1 đến Lớp N/2                                                            |
| [GPU 1: cuda:1] -> Lớp (N/2 + 1) đến Lớp N                                                       |
| -> Nhược điểm: Tạo bọt khí trễ (Pipeline Bubble), nghẽn băng thông PCIe trên các card không NVLink|
+--------------------------------------------------------------------------------------------------+

+--------------------------------------------------------------------------------------------------+
| TRƯỜNG PHÁI 3: TENSOR PARALLELISM (Megatron-LM / vLLM / DeepSpeed)                               |
| [GPU 0 & GPU 1] -> Chia nhỏ phép nhân ma trận trọng số (Q, K, V Projections)                     |
| -> Nhược điểm: Bắt buộc có phần cứng NVLink băng thông cao; Không hiệu quả trên GPU PCIe như T4. |
+--------------------------------------------------------------------------------------------------+

+--------------------------------------------------------------------------------------------------+
| TRƯỜNG PHÁI 4: DISTRIBUTED DATA PARALLEL (DDP via torch.multiprocessing)                         |
| [Process 0 on GPU 0] -> Nạp full model, xử lý Batch Nửa đầu dữ liệu                              |
| [Process 1 on GPU 1] -> Nạp full model, xử lý Batch Nửa sau dữ liệu                              |
| -> Ưu điểm: Khử hoàn toàn khóa GIL; Tăng tốc x2 tuyến tính; Tối ưu cho sản xuất khối lượng lớn. |
+--------------------------------------------------------------------------------------------------+
```

### Bảng Đối Chiếu Quyết Định Kỹ Thuật (Decision Matrix)

| Tiêu chí | 1. Tower Sharding | 2. Pipeline (`device_map`) | 3. Tensor Parallel | 4. DDP (Multi-Process) |
| :--- | :---: | :---: | :---: | :---: |
| **Độ trễ truyền tin qua PCIe** | **0 ms (Tuyệt đối)** | Cao (Chờ từng layer) | Rất cao (All-Reduce liên tục) | **0 ms (Độc lập)** |
| **Độ ổn định & Không lỗi Hook** | **100% (An toàn nhất)** | Trung bình | Thấp trên mô hình nhỏ | **100% (Rất cao)** |
| **Tận dụng 2x GPU T4** | Cực tốt (1 GPU Ảnh, 1 GPU Chữ) | Trung bình | Kém | Tối đa (x2 tốc độ) |
| **Môi trường phù hợp** | **Phase 2 Benchmark** | Model đơn >10B params | Server A100/H100 NVLink | **Phase 3 Mass Vectorization** |

---

## 3. Các Mẫu Triển Khai Thực Chiến (Production Implementation Patterns)

### Mẫu 1: Mini-Batching Stream An Toàn Tuyệt Đối (Ngăn Ngừa OOM)
Áp dụng cho mọi hàm trích xuất vector ảnh và văn bản để giữ VRAM luôn dưới 1.5GB:

```python
@torch.no_grad()
def get_image_embeddings(self, images: list, batch_size: int = 32) -> np.ndarray:
    if self.model is None or not images:
        return np.zeros((len(images), self.dim), dtype=np.float32)
        
    all_vecs = []
    for i in range(0, len(images), batch_size):
        batch_imgs = images[i : i + batch_size]
        
        # 1. Trích xuất đặc trưng theo lô nhỏ (32 ảnh)
        inputs = self.processor(images=batch_imgs, return_tensors="pt").to(self.device)
        outputs = self.model.get_image_features(**inputs) if hasattr(self.model, "get_image_features") else self.model(**inputs)
        
        # 2. Bóc tách ModelOutput an toàn
        if hasattr(outputs, "image_embeds") and outputs.image_embeds is not None:
            tensor = outputs.image_embeds
        elif hasattr(outputs, "pooler_output") and outputs.pooler_output is not None:
            tensor = outputs.pooler_output
        elif hasattr(outputs, "last_hidden_state") and outputs.last_hidden_state is not None:
            tensor = outputs.last_hidden_state[:, 0, :]
        elif isinstance(outputs, (tuple, list)):
            tensor = outputs[0]
        else:
            tensor = outputs
            
        # 3. Chuẩn hóa L2 và gom về mảng numpy
        features = F.normalize(tensor, p=2, dim=-1)
        all_vecs.append(features.cpu().numpy().astype(np.float32))
        
    return np.vstack(all_vecs)
```

---

### Mẫu 2: Phân Tách Tháp Thị Giác / Ngôn Ngữ Trên Dual-GPU (Tower Sharding)
Đặt Vision Tower lên GPU 0 và Text Tower lên GPU 1:

```python
class TowerShardedCLIP:
    def __init__(self, model_name: str):
        from transformers import AutoProcessor, AutoModel
        self.processor = AutoProcessor.from_pretrained(model_name)
        full_model = AutoModel.from_pretrained(model_name)
        
        # Đưa Vision Tower sang GPU 0
        self.vision_model = full_model.vision_model.to("cuda:0").eval()
        self.visual_projection = getattr(full_model, "visual_projection", None)
        if self.visual_projection is not None:
            self.visual_projection = self.visual_projection.to("cuda:0")
            
        # Đưa Text Tower sang GPU 1
        self.text_model = full_model.text_model.to("cuda:1").eval()
        self.text_projection = getattr(full_model, "text_projection", None)
        if self.text_projection is not None:
            self.text_projection = self.text_projection.to("cuda:1")

    @torch.no_grad()
    def embed_images(self, images: list, batch_size: int = 32):
        # Chạy hoàn toàn độc lập trên cuda:0
        inputs = self.processor(images=images, return_tensors="pt").to("cuda:0")
        features = self.vision_model(**inputs).pooler_output
        if self.visual_projection is not None:
            features = self.visual_projection(features)
        return F.normalize(features, p=2, dim=-1).cpu().numpy()

    @torch.no_grad()
    def embed_texts(self, texts: list, batch_size: int = 64):
        # Chạy hoàn toàn độc lập trên cuda:1
        inputs = self.processor(text=texts, padding=True, truncation=True, return_tensors="pt").to("cuda:1")
        features = self.text_model(**inputs).pooler_output
        if self.text_projection is not None:
            features = self.text_projection(features)
        return F.normalize(features, p=2, dim=-1).cpu().numpy()
```

---

## 4. Cẩm Nang Khắc Phục Lỗi Phổ Biến (Gotchas & Troubleshooting Checklist)

### Gotcha 1: `NameError: name '__file__' is not defined`
* **Triệu chứng:** Xảy ra khi chạy script `.py` chuyển thành Jupyter Notebook trên Kaggle (`/tmp/ipykernel_...`).
* **Giải pháp chuẩn:**
  ```python
  def get_base_dir() -> str:
      if "__file__" in globals():
          return os.path.dirname(os.path.abspath(__file__))
      return os.getcwd()
  ```

### Gotcha 2: `AttributeError: 'BaseModelOutputWithPooling' object has no attribute 'norm'`
* **Triệu chứng:** Gọi trực tiếp `F.normalize(features)` khi `features` là đối tượng bao ngoài của HuggingFace.
* **Giải pháp chuẩn:** Bóc tách `.pooler_output` hoặc `.image_embeds` trước khi gọi `F.normalize`.

### Gotcha 3: `Tensor.item() cannot be called on meta tensors` (Mô hình Jina-CLIP)
* **Triệu chứng:** Transformers 4.40+ mặc định bật `low_cpu_mem_usage=True` khiến mã nguồn Jina gọi `.item()` trên tensor ảo.
* **Giải pháp chuẩn (Jina Shield):**
  ```python
  original_context_managers = getattr(transformers.modeling_utils, "ContextManagers", None)
  if original_context_managers is not None:
      transformers.modeling_utils.ContextManagers = lambda ctx: contextlib.nullcontext()
  try:
      self.model = AutoModel.from_pretrained(
          model_name, 
          trust_remote_code=True, 
          low_cpu_mem_usage=False, 
          torch_dtype=torch.float32
      ).to(self.device).eval()
  finally:
      if original_context_managers is not None:
          transformers.modeling_utils.ContextManagers = original_context_managers
  ```

### Gotcha 4: `Can't load image processor for apple/DFN2B-CLIP-ViT-B-16`
* **Triệu chứng:** Trọng số Apple DFN2B trên HuggingFace không có `preprocessor_config.json` tiêu chuẩn.
* **Giải pháp chuẩn:** Nạp qua adapter của OpenCLIP:
  ```python
  self.model, _, self.preprocess = open_clip.create_model_and_transforms(
      "hf-hub:apple/DFN2B-CLIP-ViT-B-16", device=self.device
  )
  self.tokenizer = open_clip.get_tokenizer("hf-hub:apple/DFN2B-CLIP-ViT-B-16")
  ```

### Gotcha 5: Dọn dẹp VRAM Triệt Để Giữa Các Lần Nạp Model (Zero Memory Leak)
* **Giải pháp chuẩn:**
  ```python
  def unload(self):
      del self.model
      del self.processor
      del self.tokenizer
      del self.preprocess
      self.model = None
      self.processor = None
      self.tokenizer = None
      self.preprocess = None
      gc.collect()
      if torch.cuda.is_available():
          torch.cuda.empty_cache()
  ```

---

## 5. Định Hướng Áp Dụng Cho Dự Án AIC 2026

1. **Giai đoạn Đánh Giá (Phase 2):** Sử dụng Single-GPU Streamlined Mini-Batching (32/64 mẫu) kết hợp đọc Virtual Cache `.blob` trực tiếp vào RAM. Thời gian chạy 10 mô hình chỉ dưới 1 phút.
2. **Giai đoạn Trích Xuất Đại Trà 1M+ Keyframes (Phase 3):** 
   - Ưu tiên 1: Google TPU v5e-8 (128GB HBM2e) theo quy chuẩn Tier 2.
   - Ưu tiên 2 (Nếu dùng GPU): DistributedDataParallel (DDP) 2 tiến trình độc lập với multi-worker DataLoader.
