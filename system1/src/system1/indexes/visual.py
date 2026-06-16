from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def write_visual_index(index_path: Path, embeddings: list[list[float]]) -> str:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    if not embeddings:
        index_path.write_bytes(json.dumps({"kind": "empty_stub_visual_index", "count": 0}).encode("utf-8") + b"\n")
        return "empty_stub"
    if importlib.util.find_spec("faiss") is None:
        index_path.write_bytes(json.dumps({"kind": "stub_visual_index", "count": len(embeddings)}).encode("utf-8") + b"\n")
        return "stub"
    import faiss  # type: ignore
    import numpy as np  # type: ignore

    matrix = np.array(embeddings, dtype="float32")
    if matrix.ndim != 2 or matrix.shape[0] == 0:
        index_path.write_bytes(json.dumps({"kind": "empty_stub_visual_index", "count": 0}).encode("utf-8") + b"\n")
        return "empty_stub"
    index = faiss.IndexFlatL2(matrix.shape[1])
    index.add(matrix)
    faiss.write_index(index, str(index_path))
    return "faiss"
