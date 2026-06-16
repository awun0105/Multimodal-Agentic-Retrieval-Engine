from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class ASRProvider(Protocol):
    def transcribe(self, video_path: Path) -> str: ...


class OCRProvider(Protocol):
    def read_text(self, image_path: Path) -> str: ...


class EmbeddingProvider(Protocol):
    model_slug: str
    embedding_dim: int

    def embed_image(self, image_path: Path) -> list[float]: ...


class ObjectDetectionProvider(Protocol):
    def detect(self, image_path: Path) -> list[str]: ...


class ImageCaptionProvider(Protocol):
    def caption(self, image_path: Path, fallback_text: str) -> str: ...


class ShotCaptionProvider(Protocol):
    def caption(self, shot_id: str, fallback_text: str) -> str: ...


class SceneSummaryProvider(Protocol):
    def summarize(self, scene_id: str, fallback_text: str) -> str: ...


@dataclass(frozen=True)
class MockEmbeddingProvider:
    model_slug: str = "mock-embedding-v1"
    embedding_dim: int = 4

    def embed_image(self, image_path: Path) -> list[float]:
        digest = hashlib.sha256(image_path.read_bytes()).digest()
        return [round(int(digest[index]) / 255.0, 6) for index in range(self.embedding_dim)]


@dataclass(frozen=True)
class MockTextProvider:
    provider_name: str = "mock"

    def transcribe(self, video_path: Path) -> str:
        return ""

    def read_text(self, image_path: Path) -> str:
        return ""

    def detect(self, image_path: Path) -> list[str]:
        return ["mock_object"]

    def caption(self, image_path: Path, fallback_text: str) -> str:
        return fallback_text

    def summarize(self, scene_id: str, fallback_text: str) -> str:
        return fallback_text


@dataclass(frozen=True)
class RealProviderUnavailable:
    provider_name: str = "real_unavailable"

    def transcribe(self, video_path: Path) -> str:
        return ""

    def read_text(self, image_path: Path) -> str:
        return ""

    def detect(self, image_path: Path) -> list[str]:
        return ["real_provider_unavailable"]

    def caption(self, image_path: Path, fallback_text: str) -> str:
        return fallback_text

    def summarize(self, scene_id: str, fallback_text: str) -> str:
        return fallback_text


@dataclass(frozen=True)
class RealEmbeddingUnavailable:
    model_slug: str = "real-embedding-unavailable"
    embedding_dim: int = 4

    def embed_image(self, image_path: Path) -> list[float]:
        digest = hashlib.sha256(image_path.read_bytes()).digest()
        return [round(int(digest[index]) / 255.0, 6) for index in range(self.embedding_dim)]
