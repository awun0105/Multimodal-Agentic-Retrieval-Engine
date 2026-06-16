from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import pandas as pd

from system1.release.types import CHECKPOINT_VERSION, BuildOptions, config_hash, write_json


def read_checkpoint(release_dir: Path) -> dict[str, Any] | None:
    path = release_dir / "manifests" / "checkpoint_manifest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_checkpoint(release_dir: Path, options: BuildOptions, tables: dict[str, pd.DataFrame]) -> None:
    videos: dict[str, dict[str, Any]] = {}
    for row in tables["_reuse"].to_dict("records"):
        videos[str(row["video_id"])] = row
    embeddings = [row["vector"] for row in tables["_embeddings"].to_dict("records")]
    payload = {
        "checkpoint_version": CHECKPOINT_VERSION,
        "mode": options.mode,
        "providers": options.providers,
        "provider_plan": (options.provider_plan.__dict__ if options.provider_plan else {}),
        "config_hash": config_hash(options),
        "created_unix": int(time.time()),
        "videos": videos,
        "embeddings_hash": hashlib.sha256(json.dumps(embeddings, sort_keys=True).encode("utf-8")).hexdigest(),
        "rules": {
            "skip_keyframe_if_input_config_schema_unchanged": True,
            "skip_faiss_if_text_only_changes": True,
            "skip_asr_ocr_if_embedding_only_changes": True,
        },
    }
    write_json(release_dir / "manifests" / "checkpoint_manifest.json", payload)
