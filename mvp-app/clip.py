"""Adaptive multilingual CLIP text and compatible CLIP image encoding."""

from __future__ import annotations

import gc
import logging
from threading import Lock
from typing import Any, cast

import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from transformers import CLIPModel, CLIPProcessor

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "sentence-transformers/clip-ViT-B-32-multilingual-v1"
DEFAULT_MODEL_REVISION = "58edf8cada9e398793dca955574a48cbb7f18be2"
DEFAULT_IMAGE_MODEL_ID = "openai/clip-vit-base-patch32"
DEFAULT_IMAGE_MODEL_REVISION = "3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268"


def _as_tensor(output: Any) -> torch.Tensor:
    if isinstance(output, torch.Tensor):
        return output
    pooled = getattr(output, "pooler_output", None)
    if isinstance(pooled, torch.Tensor):
        return pooled
    raise TypeError(
        f"Unexpected CLIP output type {type(output).__name__}; "
        "expected torch.Tensor or an object with pooler_output."
    )


def _normalize(vectors: np.ndarray) -> np.ndarray:
    matrix = np.asarray(vectors, dtype=np.float32)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise ValueError("CLIP returned a zero-magnitude embedding")
    return np.ascontiguousarray(matrix / norms, dtype=np.float32)


class CLIPSearcher:
    """Multilingual runtime text encoder plus a separate release image encoder."""

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        revision: str = DEFAULT_MODEL_REVISION,
        device: str | None = None,
        image_model_id: str = DEFAULT_IMAGE_MODEL_ID,
        image_model_revision: str = DEFAULT_IMAGE_MODEL_REVISION,
    ) -> None:
        self.model_id = model_id
        self.revision = revision
        self.image_model_id = image_model_id
        self.image_model_revision = image_model_revision
        self._device = device
        self._allow_cpu_fallback = device is None
        self._model: SentenceTransformer | None = None
        self._image_model: CLIPModel | None = None
        self._processor: CLIPProcessor | None = None
        self._load_lock = Lock()
        self._image_load_lock = Lock()

    @property
    def device(self) -> str:
        return self._device or ("cuda" if torch.cuda.is_available() else "cpu")

    @property
    def dtype(self) -> torch.dtype:
        return torch.float16 if self.device == "cuda" else torch.float32

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def is_image_model_loaded(self) -> bool:
        return self._image_model is not None

    def load(self) -> None:
        """Preload only the multilingual runtime text model."""
        self._ensure_loaded()

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            try:
                self._model = self._load_text_model()
            except torch.OutOfMemoryError:
                if not self._allow_cpu_fallback or self.device != "cuda":
                    raise
                logger.warning(
                    "Not enough CUDA memory for multilingual CLIP; retrying on CPU"
                )
            else:
                return

            # Retry after leaving the exception block so its traceback cannot
            # retain partially allocated CUDA tensors.
            self._device = "cpu"
            gc.collect()
            torch.cuda.empty_cache()
            self._model = self._load_text_model()

    def _load_text_model(self) -> SentenceTransformer:
        logger.info(
            "Loading multilingual CLIP text model %s on %s with %s",
            self.model_id,
            self.device,
            self.dtype,
        )
        model_cls = cast(Any, SentenceTransformer)
        model = cast(
            SentenceTransformer,
            model_cls(
                self.model_id,
                revision=self.revision,
                device=self.device,
                model_kwargs={"torch_dtype": self.dtype},
            ),
        )
        if self.dtype == torch.float16:
            model.half()
        else:
            model.float()
        model.eval()
        return model

    def _move_text_model_to_cpu(self) -> None:
        with self._load_lock:
            if self._model is None or self.device != "cuda":
                return
            logger.warning("CUDA ran out of memory during CLIP inference; switching to CPU")
            self._model.to("cpu")
            self._model.float()
            self._model.eval()
            self._device = "cpu"
            gc.collect()
            torch.cuda.empty_cache()

    @torch.no_grad()
    def get_text_features(self, text: str) -> np.ndarray:
        self._ensure_loaded()
        assert self._model is not None
        try:
            output = self._model.encode(
                [text],
                convert_to_numpy=True,
                normalize_embeddings=False,
                show_progress_bar=False,
            )
        except torch.OutOfMemoryError:
            if not self._allow_cpu_fallback or self.device != "cuda":
                raise
        else:
            return _normalize(output)

        self._move_text_model_to_cpu()
        output = self._model.encode(
            [text],
            convert_to_numpy=True,
            normalize_embeddings=False,
            show_progress_bar=False,
        )
        return _normalize(output)

    def _ensure_image_loaded(self) -> None:
        """Load the compatible image encoder only for offline release tooling."""
        if self._image_model is not None:
            return
        with self._image_load_lock:
            if self._image_model is not None:
                return
            logger.info(
                "Loading CLIP image model %s on %s with %s",
                self.image_model_id,
                self.device,
                self.dtype,
            )
            model_cls = cast(Any, CLIPModel)
            model = cast(
                Any,
                model_cls.from_pretrained(
                    self.image_model_id,
                    revision=self.image_model_revision,
                    torch_dtype=self.dtype,
                ),
            )
            model.to(self.device)
            model.eval()
            self._image_model = cast(CLIPModel, model)
            self._processor = CLIPProcessor.from_pretrained(
                self.image_model_id,
                revision=self.image_model_revision,
            )

    @torch.no_grad()
    def get_image_batch_features(self, images: list[Any]) -> np.ndarray:
        if not images:
            return np.empty((0, 512), dtype=np.float32)
        self._ensure_image_loaded()
        assert self._processor is not None and self._image_model is not None
        inputs = self._processor(images=images, return_tensors="pt").to(self.device)
        output = _as_tensor(self._image_model.get_image_features(**inputs))
        output = output.detach().cpu().numpy()
        return _normalize(output)

    def get_image_features(self, image: Any) -> np.ndarray:
        return self.get_image_batch_features([image])
