"""
AIC 2026 UNIFIED VISION EMBEDDING LOADER.
Ho tro quan ly va tai cac mo hinh Vision Transformer (ViT):
- SigLIP SO400M (google/siglip-so400m-patch14-384) -> 1152d Visual Feature
- ViSigLIP-OT (bkai-foundation-models/vietnamese-bi-encoder) -> 768d Vietnamese Visual-Text Feature
- SigLIP Base (google/siglip-base-patch16-224) -> 768d Base Feature
- CLIP ViT-Large/14 (openai/clip-vit-large-patch14) -> 768d Fallback
"""

from __future__ import annotations
import os
import sys
import torch
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

# Dam bao UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


class VisionEmbeddingLoader:
    _models: Dict[str, Any] = {}
    _processors: Dict[str, Any] = {}

    @classmethod
    def get_device(cls, prefer_tpu: bool = False) -> str:
        """Phat hien phan cung toi uu (TPU -> CUDA GPU -> CPU)."""
        if prefer_tpu:
            try:
                import torch_xla.core.xla_model as xm
                return xm.xla_device()
            except ImportError:
                pass
        if torch.cuda.is_available():
            return "cuda"
        return "cpu"

    @classmethod
    def load_siglip_so400m(cls, device: Optional[str] = None):
        """Tai mo hinh Vision Transformer SigLIP SO400M (1152d)."""
        model_id = "google/siglip-so400m-patch14-384"
        if device is None:
            device = cls.get_device()

        if model_id in cls._models:
            return cls._models[model_id], cls._processors[model_id]

        try:
            from transformers import AutoProcessor, AutoModel
            print(f"[Embedding Loader] Dang tai SigLIP SO400M ({model_id}) tren {device}...")
            processor = AutoProcessor.from_pretrained(model_id)
            model = AutoModel.from_pretrained(model_id)
            model.to(device)
            model.eval()

            cls._models[model_id] = model
            cls._processors[model_id] = processor
            print(f"[Embedding Loader] Tai thanh cong SigLIP SO400M (1152d)!")
            return model, processor
        except Exception as e:
            print(f"[Embedding Loader] Khong the tai {model_id}: {e}")
            return None, None

    @classmethod
    def load_visiglip_vietnamese(cls, device: Optional[str] = None):
        """Tai mo hinh ViSigLIP-OT chuyen biet tieng Viet (768d)."""
        model_id = "bkai-foundation-models/vietnamese-bi-encoder"
        if device is None:
            device = cls.get_device()

        if model_id in cls._models:
            return cls._models[model_id], cls._processors[model_id]

        try:
            from transformers import AutoTokenizer, AutoModel
            print(f"[Embedding Loader] Dang tai ViSigLIP Vietnamese ({model_id}) tren {device}...")
            tokenizer = AutoTokenizer.from_pretrained(model_id)
            model = AutoModel.from_pretrained(model_id)
            model.to(device)
            model.eval()

            cls._models[model_id] = model
            cls._processors[model_id] = tokenizer
            print(f"[Embedding Loader] Tai thanh cong ViSigLIP (768d)!")
            return model, tokenizer
        except Exception as e:
            print(f"[Embedding Loader] Khong the tai {model_id}: {e}")
            return None, None
