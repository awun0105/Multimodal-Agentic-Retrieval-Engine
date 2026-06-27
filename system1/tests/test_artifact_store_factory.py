from __future__ import annotations

import pytest

from system1.artifacts import (
    ArtifactStore,
    HuggingFaceDatasetArtifactStore,
    artifact_store_config_from_env,
    make_artifact_store_from_config,
    make_artifact_store_from_env,
)


def test_default_env_gives_local_backend_config(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AIC_ARTIFACT_BACKEND", raising=False)
    monkeypatch.delenv("AIC_ARTIFACT_ROOT", raising=False)
    config = artifact_store_config_from_env()
    assert config.backend == "local"
    assert config.artifact_root == (tmp_path / "system1_artifacts").resolve()


def test_local_backend_returns_local_artifact_store(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIC_ARTIFACT_BACKEND", "local")
    monkeypatch.setenv("AIC_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    store = make_artifact_store_from_env()
    assert isinstance(store, ArtifactStore)


def test_hf_dataset_without_repo_id_raises(tmp_path) -> None:
    with pytest.raises(ValueError):
        make_artifact_store_from_config(
            artifact_store_config_from_env(artifact_root=tmp_path / "artifacts", backend="hf_dataset")
        )


def test_hf_env_priority_fields(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AIC_HF_REPO_ID", "org/repo")
    monkeypatch.setenv("AIC_HF_REPO_TYPE", "dataset")
    monkeypatch.setenv("AIC_HF_REVISION", "branch-x")
    monkeypatch.setenv("AIC_HF_PREFIX", "prefix-x")
    config = artifact_store_config_from_env(backend="hf_dataset")
    assert config.hf_repo_id == "org/repo"
    assert config.hf_repo_type == "dataset"
    assert config.hf_revision == "branch-x"
    assert config.hf_prefix == "prefix-x"


def test_token_priority_aic_hf_token_beats_hf_token(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AIC_HF_TOKEN", "aic-token")
    monkeypatch.setenv("HF_TOKEN", "hf-token")
    config = artifact_store_config_from_env(backend="hf_dataset", hf_repo_id="org/repo")
    assert config.hf_token == "aic-token"


def test_hf_backend_returns_hf_store(tmp_path) -> None:
    store = make_artifact_store_from_config(
        artifact_store_config_from_env(
            artifact_root=tmp_path / "artifacts",
            backend="hf_dataset",
            hf_repo_id="org/repo",
            hf_prefix="runs/abc",
        )
    )
    assert isinstance(store, HuggingFaceDatasetArtifactStore)
    assert store.repo_id == "org/repo"
    assert store.prefix == "runs/abc"
