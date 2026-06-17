from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from system1.config import ProviderPlan
from system1.runtime.environment import resolve_runtime_environment

DEFAULT_RELEASE_ID = "competition_dataset_v001"
RELEASE_NAME = DEFAULT_RELEASE_ID  # legacy alias for old code/tests
DEFAULT_FRAME_ID = 0
INDEX_NAME = "visual"
INDEX_VERSION = "v001"
CHECKPOINT_VERSION = "v001"


@dataclass(frozen=True)
class BuildOptions:
    mode: str = "debug_small_sample"
    providers: str = "mock"
    provider_plan: ProviderPlan | None = None



def current_release_id() -> str:
    return resolve_runtime_environment().release_name

def release_root(output_dir: Path | str) -> Path:
    return Path(output_dir) / current_release_id()

def default_input_dir() -> Path:
    return resolve_runtime_environment().input_root


def config_dir() -> Path:
    return resolve_runtime_environment().config_root


def create_release_directories(release_dir: Path) -> None:
    for relative_path in (
        "db",
        "indexes",
        "media/keyframes",
        "media/thumbnails",
        "media/dense_frame_cache",
        "tables",
        "manifests",
        "raw_mapping",
    ):
        (release_dir / relative_path).mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def config_hash(options: BuildOptions) -> str:
    plan = options.provider_plan.__dict__ if options.provider_plan else {}
    payload = {"mode": options.mode, "providers": options.providers, "provider_plan": plan}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
