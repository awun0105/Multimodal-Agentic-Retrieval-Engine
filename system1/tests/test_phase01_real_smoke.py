from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from system1.config import load_configs
from system1.phase01 import smoke


CONFIG_DIR = Path(__file__).resolve().parents[1] / "configs"


def _settings() -> dict[str, str]:
    return {
        "batch_id": "batch_000",
        "worker_id": "worker_000",
        "hf_checkpoint_repo": "org/production-checkpoints",
        "checkpoint_revision": "model-artifacts-v1",
    }


def test_smoke_config_isolates_writes_but_keeps_production_model_store() -> None:
    policy = load_configs(CONFIG_DIR)["phase01"]["smoke"]
    resolved = smoke._resolve_smoke_config(
        config_dir=CONFIG_DIR,
        production_user_settings=_settings(),
        smoke_policy=policy,
        namespace="_smoke/run_123",
        batch_id="smoke_run_123",
        worker_id="smoke_run_123",
    )

    assert resolved.payload["storage"]["release"]["repo_id"] == (
        "1thesudden/AIOU26_release_test"
    )
    assert resolved.payload["storage"]["release"]["prefix"] == "_smoke/run_123"
    assert resolved.payload["storage"]["checkpoint"]["repo_id"] == (
        "1thesudden/AIOU26_checkpoints_test"
    )
    assert resolved.payload["storage"]["checkpoint"]["prefix"] == "_smoke/run_123"
    assert resolved.payload["storage"]["model_artifacts"]["repo_id"] == (
        "org/production-checkpoints"
    )
    assert resolved.payload["storage"]["model_artifacts"]["revision"] == (
        "model-artifacts-v1"
    )


def test_remote_cleanup_enumerates_exact_files_and_enforces_guards() -> None:
    class Store:
        repo_id = "org/test"
        prefix = "_smoke/run_123"

        def __init__(self) -> None:
            self.deleted: list[str] = []

        def list_files(self, _prefix: str):
            return [Path("a/file.json"), Path("b/file.zip")]

        def sync_files(self, files, *, delete_paths, **_kwargs):
            assert files == []
            self.deleted = list(delete_paths)

    store = Store()
    smoke._delete_smoke_files(store, configured_repo="org/test", run_id="run_123")
    assert store.deleted == ["a/file.json", "b/file.zip"]

    store.prefix = "canonical_release_v001"
    with pytest.raises(ValueError, match="unsafe remote smoke deletion"):
        smoke._delete_smoke_files(
            store, configured_repo="org/test", run_id="run_123"
        )


def test_smoke_mapping_accepts_source_branch_then_execution_pins_commit() -> None:
    policy = load_configs(CONFIG_DIR)["phase01"]["smoke"]
    raw = policy["source_raw"]
    mapping = {
        "canonical_repo_id": raw["repo_id"],
        "canonical_revision": "main",
        "canonical_prefix": "canonical_raw_v001",
        "canonical_video_path": "raw_videos/L30_V040.mp4",
        "canonical_metadata_path": "metadata/L30_V040.json",
    }

    assert smoke._validate_mapping(mapping, raw) == "main"


def test_parquet_sample_serializes_multivalue_array_fields() -> None:
    parquet = io.BytesIO()
    pd.DataFrame(
        [
            {
                "caption_vi": "Một chú mèo đang nằm trên ghế.",
                "objects_vi": np.array(["mèo", "ghế"], dtype=object),
                "scores": np.array([0.9, 0.8]),
            }
        ]
    ).to_parquet(parquet, index=False)

    package = io.BytesIO()
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("L30_V040/shot_captions.parquet", parquet.getvalue())
    package.seek(0)

    with zipfile.ZipFile(package) as archive:
        sample = smoke._parquet_sample(
            archive,
            "L30_V040",
            "shot_captions.parquet",
            preferred_text_fields=("caption_vi",),
            require_text=True,
        )

    assert sample == {
        "caption_vi": "Một chú mèo đang nằm trên ghế.",
        "objects_vi": ["mèo", "ghế"],
        "scores": [0.9, 0.8],
    }
