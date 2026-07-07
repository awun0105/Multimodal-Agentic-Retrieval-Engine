from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from system1.indexes.visual import write_visual_index
from system1.release.types import INDEX_NAME, INDEX_VERSION, write_json


def build_visual_index(release_dir: Path | str) -> Path:
    release_path = Path(release_dir)
    embeddings_meta_path = release_path / "tables" / "embeddings_meta.parquet"
    if not embeddings_meta_path.exists():
        raise FileNotFoundError("missing merged embeddings_meta.parquet; run system1 merge first")
    embeddings_meta = pd.read_parquet(embeddings_meta_path)
    vectors: list[list[float]] = []
    vector_rows: list[dict[str, object]] = []
    vector_id = 0
    for video_id in embeddings_meta["video_id"].astype(str).unique().tolist():
        feature_dir = release_path / "artifacts" / "features" / video_id
        embeddings_file = feature_dir / "visual_embeddings.npy"
        if not embeddings_file.exists():
            raise FileNotFoundError(f"missing feature embeddings for {video_id}: {embeddings_file}")
        matrix = np.load(embeddings_file)
        rows = embeddings_meta[embeddings_meta["video_id"].astype(str) == video_id].reset_index(drop=True)
        if len(rows) != len(matrix):
            raise ValueError(f"embedding row count mismatch for {video_id}: meta={len(rows)} vectors={len(matrix)}")
        for idx, row in rows.iterrows():
            vector = matrix[idx].tolist()
            vectors.append(vector)
            vector_rows.append({
                "index_name": INDEX_NAME,
                "index_version": INDEX_VERSION,
                "embedding_model": row["embedding_model"],
                "vector_id": vector_id,
                "embedding_id": row["embedding_id"],
                "keyframe_id": row["keyframe_id"],
                "video_id": row["video_id"],
                "frame_id": row["frame_id"],
            })
            vector_id += 1
    vector_map = pd.DataFrame(vector_rows)
    indexes_dir = release_path / "indexes"
    indexes_dir.mkdir(parents=True, exist_ok=True)
    vector_map.to_parquet(indexes_dir / "vector_map.parquet", index=False)
    index_path = indexes_dir / "visual.faiss"
    kind = write_visual_index(index_path, vectors)
    warnings = []
    if (release_path / "db" / "app.sqlite").exists():
        warnings.append("db/app.sqlite exists; rerun system1 build-db to include updated vector_map")
    write_json(
        indexes_dir / "index_version.json",
        {"index_name": INDEX_NAME, "index_version": INDEX_VERSION, "index_backend": kind, "vector_count": len(vector_rows), "warnings": warnings},
    )
    return index_path

