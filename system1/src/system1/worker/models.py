"""Construct the real worker providers once per session.

Captions use the second GPU when two are present (Kaggle T4 x2); the other
models share the first. Measured placement: docs/plans/active/
system1-pipeline-simplification.md, worker v3 run.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from system1.worker.video import WorkerModels


def load_worker_models(config: Mapping[str, Any], cache_root: Path, *, captions: bool = True) -> WorkerModels:
    import torch

    from system1.providers.asr import ChunkFormerAsr
    from system1.providers.captions import QwenCaptioner
    from system1.providers.cuts import TransNetCuts
    from system1.providers.image_embedding import SiglipEmbedder
    from system1.providers.ocr import EasyVietOcr
    from system1.providers.text_embedding import E5TextEmbedder

    if not torch.cuda.is_available():
        raise RuntimeError("the worker needs a CUDA GPU")
    models = config["models"]
    caption_device = "cuda:1" if torch.cuda.device_count() > 1 else "cuda:0"
    return WorkerModels(
        cuts=TransNetCuts(models["shot_detection"], config["model_artifacts"], cache_root / "model_artifacts"),
        image=SiglipEmbedder(models["image_embedding"], device="cuda:0"),
        asr=ChunkFormerAsr(models["asr"], device="cuda:0"),
        ocr=EasyVietOcr(models["ocr"], device="cuda:0"),
        captioner=QwenCaptioner(models["captions"], device=caption_device) if captions else None,
        text=E5TextEmbedder(models["text_embedding"], device="cuda:0"),
    )
