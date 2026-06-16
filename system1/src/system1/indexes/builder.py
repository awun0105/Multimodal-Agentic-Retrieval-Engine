from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from system1.indexes.visual import write_visual_index
from system1.release.types import INDEX_NAME, INDEX_VERSION, write_json


def write_index_files(release_dir: Path, tables: dict[str, pd.DataFrame], previous_checkpoint: dict[str, Any] | None) -> str:
    tables["vector_map"].to_parquet(release_dir / "indexes" / "vector_map.parquet", index=False)
    embeddings = [row["vector"] for row in tables["_embeddings"].to_dict("records")]
    embeddings_hash = hashlib.sha256(json.dumps(embeddings, sort_keys=True).encode("utf-8")).hexdigest()
    index_path = release_dir / "indexes" / "visual.faiss"
    previous_hash = (previous_checkpoint or {}).get("embeddings_hash")
    if previous_hash == embeddings_hash and index_path.exists():
        kind = json.loads((release_dir / "indexes" / "index_version.json").read_text(encoding="utf-8")).get("index_backend", "stub") if (release_dir / "indexes" / "index_version.json").exists() else "stub"
    else:
        kind = write_visual_index(index_path, embeddings)
    write_json(release_dir / "indexes" / "index_version.json", {"index_name": INDEX_NAME, "index_version": INDEX_VERSION, "index_backend": kind})
    return kind
