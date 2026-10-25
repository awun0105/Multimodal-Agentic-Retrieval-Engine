"""Inner-product FAISS indexes over L2-normalized vectors (ADR 0023).

One index per embedding model. Scores are cosine similarity. Each index has a
vector map `{name}_vector_map.parquet` whose row `i` names the item behind
vector `i` (a `keyframe_id` for image indexes, a `doc_id` for text indexes).
Invalid input raises instead of writing a placeholder file (ADR 0024).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import faiss
import numpy as np
import pandas as pd


def build_vector_index(
    index_dir: Path | str, name: str, vectors: np.ndarray, item_ids: Sequence[str]
) -> Path:
    matrix = _normalized(vectors, item_ids)
    index = faiss.IndexFlatIP(matrix.shape[1])
    index.add(matrix)
    root = Path(index_dir)
    root.mkdir(parents=True, exist_ok=True)
    index_path = root / f"{name}.faiss"
    faiss.write_index(index, str(index_path))
    pd.DataFrame({"vector_id": range(len(item_ids)), "item_id": list(item_ids)}).to_parquet(
        root / f"{name}_vector_map.parquet", index=False
    )
    return index_path


def load_vector_index(index_dir: Path | str, name: str) -> tuple[faiss.Index, list[str]]:
    root = Path(index_dir)
    index = faiss.read_index(str(root / f"{name}.faiss"))
    vector_map = pd.read_parquet(root / f"{name}_vector_map.parquet").sort_values("vector_id")
    item_ids = vector_map["item_id"].astype(str).tolist()
    if len(item_ids) != index.ntotal:
        raise ValueError(f"vector map has {len(item_ids)} rows, index has {index.ntotal} vectors")
    return index, item_ids


def search(
    index: faiss.Index, item_ids: Sequence[str], queries: np.ndarray, *, top_k: int
) -> list[list[tuple[str, float]]]:
    scores, positions = index.search(_normalized(queries), top_k)
    return [
        [(item_ids[position], float(score)) for position, score in zip(row_positions, row_scores)
         if position >= 0]
        for row_positions, row_scores in zip(positions, scores)
    ]


def _normalized(vectors: np.ndarray, item_ids: Sequence[str] | None = None) -> np.ndarray:
    matrix = np.ascontiguousarray(np.asarray(vectors, dtype="float32"))
    if matrix.ndim != 2 or matrix.shape[0] == 0:
        raise ValueError("expected a non-empty 2-D vector array")
    if item_ids is not None and len(item_ids) != matrix.shape[0]:
        raise ValueError(f"{matrix.shape[0]} vectors but {len(item_ids)} item IDs")
    if not np.isfinite(matrix).all():
        raise ValueError("vectors contain NaN or infinity")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if (norms == 0).any():
        raise ValueError("vectors contain an all-zero row")
    return matrix / norms
