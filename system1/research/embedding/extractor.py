"""
Module Trích xuất Đặc trưng Đa phương thức (Multimodal Embedding Extractor).

Mô tả:
Đây là mã nguồn lõi của phân hệ Embedding, hiện thực hóa Bước 3 trong Lộ trình Nghiên cứu. 
Nhiệm vụ của module là trừu tượng hóa (encapsulate) các mô hình SOTA (SigLIP, CLIP, Jina-CLIP, BGE) 
thành một giao diện duy nhất: hàm `get_vector(input_data)`.

Đặc tả kỹ thuật:
- Tự động nhận diện phần cứng (CPU/GPU) và xử lý ngoại lệ nếu thiếu thư viện (Fallback mode).
- Bắt buộc chuẩn hóa L2 (L2 Normalization) cho mọi vector đầu ra để phục vụ thuật toán Cosine Similarity trong FAISS.
- Hỗ trợ đa định dạng đầu vào: Đường dẫn tệp hình ảnh, đối tượng PIL Image, hoặc Chuỗi văn bản thô.
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import Union, List, Optional
import numpy as np

logger = logging.getLogger(__name__)

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    Image = None
    HAS_PIL = False

try:
    import torch
    from transformers import AutoProcessor, AutoModel, SiglipModel, CLIPModel
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


class SigLIPEmbeddingExtractor:
    """
    Multimodal Embedding Extractor supporting SOTA models:
    - google/siglip-base-patch16-224 (Canonical System 1 Default - 768d)
    - openai/clip-vit-base-patch32 (Baseline - 512d)
    - google/siglip-so400m-patch14-384 (High-Res - 1152d)
    - jinaai/jina-clip-v1 / jina-clip-v2 (Multilingual - 768d)
    - BAAI/bge-visualized-m3 (Multilingual Visual - 1024d)
    
    Output: L2-normalized 1D numpy vector (shape: (dimension,))
    """
    def __init__(self, model_name: str = "google/siglip-base-patch16-224", device: Optional[str] = None):
        self.model_name = model_name
        self.has_torch = HAS_TORCH
        self.has_pil = HAS_PIL
        self._is_initialized = False
        self._processor = None
        self._model = None
        
        if self.has_torch:
            self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = "cpu"

    def _ensure_initialized(self) -> None:
        if self._is_initialized:
            return

        if not self.has_torch or not self.has_pil:
            logger.warning("PyTorch or PIL unavailable. Operating in lightweight fallback mode.")
            self._is_initialized = True
            return

        try:
            print(f"[INFO] Initializing EmbeddingExtractor ({self.model_name}) on {self.device}...")
            self._processor = AutoProcessor.from_pretrained(self.model_name, trust_remote_code=True)
            if "clip" in self.model_name.lower() and "jina" not in self.model_name.lower():
                self._model = CLIPModel.from_pretrained(self.model_name).to(self.device)
            elif "siglip" in self.model_name.lower():
                self._model = SiglipModel.from_pretrained(self.model_name).to(self.device)
            else:
                self._model = AutoModel.from_pretrained(self.model_name, trust_remote_code=True).to(self.device)
                
            self._model.eval()
            print(f"[SUCCESS] Model '{self.model_name}' loaded successfully.")
        except Exception as e:
            print(f"[WARNING] Could not load model weights for {self.model_name}: {e}. Fallback mode active.")
            self._processor = None
            self._model = None

        self._is_initialized = True

    def _l2_normalize(self, vector: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(vector, ord=2)
        if norm == 0:
            return vector
        return vector / norm

    def get_vector(self, input_data: Union[str, Path, Image.Image]) -> np.ndarray:
        """
        Extract L2-normalized embedding vector for an Image or Text Query.
        """
        self._ensure_initialized()
        dim = 768
        if "clip" in self.model_name.lower() and "jina" not in self.model_name.lower():
            dim = 512
        elif "so400m" in self.model_name.lower():
            dim = 1152
        elif "bge" in self.model_name.lower():
            dim = 1024

        if self._model is None or self._processor is None:
            return np.zeros((dim,), dtype=np.float32)

        # Case 1: Image input (Path or PIL Image)
        is_image = False
        if isinstance(input_data, (Path, str)):
            p = Path(input_data)
            if p.exists() and p.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]:
                is_image = True
                input_data = Image.open(p).convert("RGB")
        elif self.has_pil and isinstance(input_data, Image.Image):
            is_image = True

        with torch.no_grad():
            if is_image:
                inputs = self._processor(images=input_data, return_tensors="pt").to(self.device)
                if hasattr(self._model, "get_image_features"):
                    outputs = self._model.get_image_features(**inputs)
                else:
                    outputs = self._model.encode_image(**inputs) if hasattr(self._model, "encode_image") else self._model(**inputs)
            else:
                text_str = str(input_data)
                inputs = self._processor(text=[text_str], return_tensors="pt", padding=True).to(self.device)
                if hasattr(self._model, "get_text_features"):
                    outputs = self._model.get_text_features(**inputs)
                else:
                    outputs = self._model.encode_text(**inputs) if hasattr(self._model, "encode_text") else self._model(**inputs)

            tensor = outputs.pooler_output if hasattr(outputs, "pooler_output") else outputs
            vec = tensor.cpu().numpy().flatten()

        return self._l2_normalize(vec)


_default_extractor = None

def get_vector(input_data: Union[str, Path], model_name: str = "google/siglip-base-patch16-224") -> np.ndarray:
    """
    Standard interface function for embedding extraction.
    """
    global _default_extractor
    if _default_extractor is None or _default_extractor.model_name != model_name:
        _default_extractor = SigLIPEmbeddingExtractor(model_name=model_name)
    return _default_extractor.get_vector(input_data)
