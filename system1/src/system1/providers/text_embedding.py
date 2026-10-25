"""Text embeddings with multilingual-e5-large (ADR 0023).

E5 expects a `passage: ` prefix on indexed text and `query: ` on queries.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def e5_passages(texts: Sequence[str]) -> list[str]:
    return [f"passage: {text}" for text in texts]


def e5_queries(texts: Sequence[str]) -> list[str]:
    return [f"query: {text}" for text in texts]


class E5TextEmbedder:
    def __init__(self, config: Mapping[str, Any], device: str = "cuda") -> None:
        from sentence_transformers import SentenceTransformer

        self.batch_size = int(config["batch_size"])
        self.model = SentenceTransformer(config["model_id"], revision=config["revision"], device=device)

    def embed_passages(self, texts: Sequence[str]):
        return self.model.encode(e5_passages(texts), batch_size=self.batch_size,
                                 normalize_embeddings=True, convert_to_numpy=True)

    def embed_queries(self, texts: Sequence[str]):
        return self.model.encode(e5_queries(texts), batch_size=self.batch_size,
                                 normalize_embeddings=True, convert_to_numpy=True)
