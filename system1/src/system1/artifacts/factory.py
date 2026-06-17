from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from system1.artifacts.hf_store import HuggingFaceDatasetArtifactStore
from system1.artifacts.store import make_artifact_store
from system1.runtime.environment import resolve_runtime_paths


@dataclass(frozen=True)
class ArtifactStoreConfig:
    backend: str
    artifact_root: Path
    hf_repo_id: str | None = None
    hf_repo_type: str = "dataset"
    hf_revision: str = "main"
    hf_token: str | None = None
    hf_prefix: str = ""


def artifact_store_config_from_env(
    *,
    artifact_root: str | Path | None = None,
    backend: str | None = None,
    hf_repo_id: str | None = None,
    hf_repo_type: str | None = None,
    hf_revision: str | None = None,
    hf_token: str | None = None,
    hf_prefix: str | None = None,
) -> ArtifactStoreConfig:
    runtime = resolve_runtime_paths()
    resolved_backend = (backend or os.environ.get("AIC_ARTIFACT_BACKEND") or "local").lower()
    resolved_artifact_root = Path(artifact_root).expanduser().resolve() if artifact_root is not None else runtime.artifact_root
    resolved_hf_repo_id = hf_repo_id or os.environ.get("AIC_HF_REPO_ID")
    resolved_hf_repo_type = hf_repo_type or os.environ.get("AIC_HF_REPO_TYPE") or "dataset"
    resolved_hf_revision = hf_revision or os.environ.get("AIC_HF_REVISION") or "main"
    resolved_hf_token = hf_token or os.environ.get("AIC_HF_TOKEN") or os.environ.get("HF_TOKEN")
    resolved_hf_prefix = hf_prefix if hf_prefix is not None else os.environ.get("AIC_HF_PREFIX", "")
    return ArtifactStoreConfig(
        backend=resolved_backend,
        artifact_root=resolved_artifact_root,
        hf_repo_id=resolved_hf_repo_id,
        hf_repo_type=resolved_hf_repo_type,
        hf_revision=resolved_hf_revision,
        hf_token=resolved_hf_token,
        hf_prefix=resolved_hf_prefix,
    )


def make_artifact_store_from_config(config: ArtifactStoreConfig):
    if config.backend == "local":
        return make_artifact_store(config.artifact_root)
    if config.backend == "hf_dataset":
        if not config.hf_repo_id:
            raise ValueError("hf_dataset backend requires hf_repo_id")
        return HuggingFaceDatasetArtifactStore(
            repo_id=config.hf_repo_id,
            repo_type=config.hf_repo_type,
            revision=config.hf_revision,
            token=config.hf_token,
            prefix=config.hf_prefix,
        )
    raise ValueError(f"Unsupported artifact backend: {config.backend}")


def make_artifact_store_from_env(**kwargs):
    return make_artifact_store_from_config(artifact_store_config_from_env(**kwargs))
