"""Construct the caption-pass providers once per session.

Qwen3-VL uses the second GPU when two are present (Kaggle T4 x2); E5 uses the
first.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def load_caption_models(config: Mapping[str, Any]) -> tuple[Any, Any]:
    """Return `(captioner, text_embedder)` built from `worker.yaml`."""

    import torch

    from system1.providers.captions import QwenCaptioner
    from system1.providers.text_embedding import E5TextEmbedder

    if not torch.cuda.is_available():
        raise RuntimeError("the caption pass needs a CUDA GPU")
    caption_device = "cuda:1" if torch.cuda.device_count() > 1 else "cuda:0"
    return (QwenCaptioner(config["captions"], device=caption_device),
            E5TextEmbedder(config["models"]["text_embedding"], device="cuda:0"))
