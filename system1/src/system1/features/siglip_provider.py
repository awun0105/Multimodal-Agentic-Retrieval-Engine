from __future__ import annotations

import logging
from dataclasses import dataclass, field
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
    from transformers import AutoProcessor, SiglipModel
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


@dataclass
class SigLIPEmbeddingProvider:
    """
    SigLIP Multimodal Embedding Provider supporting image & text embedding.
    Fully aligned with System 1 EmbeddingProvider Protocol.
    
    Features:
    - Auto CUDA/CPU device selection (works on GPU and CPU-only teammate machines).
    - Mandatory L2 normalization for vector inner-product search (FAISS IndexFlatIP).
    - Multi-variant text query embedding (supports 1-3 translation variants).
    """
    model_slug: str = "google/siglip-base-patch16-224"
    embedding_dim: int = 768
    device: Optional[str] = None
    
    _processor: Optional[object] = field(default=None, init=False, repr=False)
    _model: Optional[object] = field(default=None, init=False, repr=False)
    _is_initialized: bool = field(default=False, init=False)

    def _ensure_initialized(self) -> None:
        if self._is_initialized:
            return

        if not HAS_TORCH or not HAS_PIL:
            logger.warning("PyTorch or PIL unavailable. Operating in fallback mode.")
            self._is_initialized = True
            return

        self.device = self.device or ("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"Initializing SigLIPEmbeddingProvider ({self.model_slug}) on device: {self.device}")

        try:
            self._processor = AutoProcessor.from_pretrained(self.model_slug)
            self._model = SiglipModel.from_pretrained(self.model_slug).to(self.device)
            self._model.eval()
            logger.info("SigLIP model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load SigLIP model weights: {e}")
            self._processor = None
            self._model = None

        self._is_initialized = True

    def _l2_normalize(self, vector: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(vector, ord=2)
        if norm == 0:
            return vector
        return vector / norm

    def embed_image(self, image_path: Path) -> list[float]:
        self._ensure_initialized()
        if self._model is None or self._processor is None:
            return [0.0] * self.embedding_dim

        image = Image.open(image_path).convert("RGB")
        inputs = self._processor(images=image, return_tensors="pt").to(self.device)
        
        with torch.no_grad():
            outputs = self._model.get_image_features(**inputs)
            tensor = outputs.pooler_output if hasattr(outputs, "pooler_output") else outputs
            vec = tensor.cpu().numpy().flatten()

        normalized_vec = self._l2_normalize(vec)
        return normalized_vec.tolist()

    def embed_text(self, text: str) -> list[float]:
        self._ensure_initialized()
        if self._model is None or self._processor is None:
            return [0.0] * self.embedding_dim

        inputs = self._processor(text=[text], return_tensors="pt", padding=True).to(self.device)
        
        with torch.no_grad():
            outputs = self._model.get_text_features(**inputs)
            tensor = outputs.pooler_output if hasattr(outputs, "pooler_output") else outputs
            vec = tensor.cpu().numpy().flatten()

        normalized_vec = self._l2_normalize(vec)
        return normalized_vec.tolist()

    def embed_text_variants(self, text_variants: List[str]) -> List[list[float]]:
        """
        Embed 1-3 translation/prompt variants into separate L2-normalized query vectors.
        """
        self._ensure_initialized()
        if self._model is None or self._processor is None:
            return [[0.0] * self.embedding_dim for _ in text_variants]

        inputs = self._processor(text=text_variants, return_tensors="pt", padding=True).to(self.device)
        
        with torch.no_grad():
            outputs = self._model.get_text_features(**inputs)
            tensor = outputs.pooler_output if hasattr(outputs, "pooler_output") else outputs
            vecs = tensor.cpu().numpy()

        result = []
        for vec in vecs:
            norm_vec = self._l2_normalize(vec)
            result.append(norm_vec.tolist())

        return result
