"""Image and query embeddings with SigLIP2 (ADR 0023)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class SiglipEmbedder:
    def __init__(self, config: Mapping[str, Any], device: str = "cuda") -> None:
        import torch
        from transformers import AutoModel, AutoProcessor

        self._torch = torch
        self.config = config
        self.device = device
        self.model = AutoModel.from_pretrained(
            config["model_id"], revision=config["revision"], dtype=torch.float16).to(device).eval()
        self.processor = AutoProcessor.from_pretrained(config["model_id"], revision=config["revision"])

    def embed_images(self, images: Sequence[Any]):
        """Return a float32 array, one row per PIL image."""

        import numpy as np

        rows = []
        size = int(self.config["batch_size"])
        for offset in range(0, len(images), size):
            inputs = self.processor(images=list(images[offset:offset + size]), return_tensors="pt")
            pixels = inputs["pixel_values"].to(self.device, dtype=self._torch.float16)
            with self._torch.no_grad():
                rows.append(_tensor(self.model.get_image_features(pixel_values=pixels)).float().cpu().numpy())
        return np.concatenate(rows) if rows else np.zeros((0, 0), dtype="float32")

    def embed_texts(self, texts: Sequence[str]):
        inputs = self.processor(text=list(texts), padding="max_length",
                                max_length=int(self.config["text_max_length"]), truncation=True,
                                return_tensors="pt").to(self.device)
        with self._torch.no_grad():
            return _tensor(self.model.get_text_features(**inputs)).float().cpu().numpy()


def _tensor(output):
    # transformers 5 may return a model output object instead of a tensor.
    return output if hasattr(output, "shape") else output.pooler_output
