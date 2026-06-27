from __future__ import annotations

from pathlib import Path
import os
import zipfile

import typer

from system1.artifacts.checkpoint import (
    checkpoint_relative_path,
    restore_checkpoint,
    save_checkpoint,
)
from system1.artifacts.factory import make_artifact_store_from_env
from system1.artifacts.hf_store import HF_EXPECTED_ERRORS
from system1.runtime.environment import resolve_runtime_environment
from system1.runtime.environment import resolve_runtime_paths
from system1.release.types import release_root

SUPPORTED_MODES = {"debug_small_sample", "bronze_fast", "silver_balanced", "gold_full"}
SUPPORTED_PROVIDERS = {"mock", "real", "config", "rule_based", "vlm"}

def default_output() -> Path:
    return resolve_runtime_environment().output_root

def runtime_paths():
    return resolve_runtime_paths()

def default_artifact_root() -> Path:
    return resolve_runtime_paths().artifact_root

def default_artifact_backend() -> str:
    return os.environ.get("AIC_ARTIFACT_BACKEND", "local")

def default_hf_repo_id() -> str | None:
    return os.environ.get("AIC_HF_REPO_ID")

def default_hf_repo_type() -> str:
    return os.environ.get("AIC_HF_REPO_TYPE", "dataset")

def default_hf_revision() -> str:
    return os.environ.get("AIC_HF_REVISION", "main")

def default_hf_prefix() -> str:
    return os.environ.get("AIC_HF_PREFIX", "")

def default_cli_resume() -> bool:
    # --- SỬA LỖI LOGIC: Luôn ưu tiên cơ chế phân giải tập trung của environment.py ---
    return resolve_runtime_paths().resume

def default_cli_sync() -> bool:
    # --- SỬA LỖI LOGIC: Luôn ưu tiên cơ chế phân giải tập trung của environment.py ---
    return resolve_runtime_paths().sync


def release_dir(output: Path) -> Path:
    return release_root(output)


def require_supported_mode(mode: str) -> None:
    if mode not in SUPPORTED_MODES:
        raise typer.BadParameter(
            "supported modes: debug_small_sample, bronze_fast, silver_balanced, gold_full"
        )


def require_supported_providers(providers: str) -> None:
    if providers not in SUPPORTED_PROVIDERS:
        raise typer.BadParameter(
            "supported providers: mock, real, config, rule_based, vlm"
        )


def require_supported_batch(batch_id: str, output: Path) -> None:
    manifest_path = release_dir(output) / "manifests" / f"{batch_id}.txt"
    if manifest_path.exists():
        return
    manifests_dir = release_dir(output) / "manifests"
    generated = sorted(path.stem for path in manifests_dir.glob("batch_*.txt")) if manifests_dir.exists() else []
    allowed = ", ".join(generated) if generated else "none generated yet"
    raise typer.BadParameter(f"missing batch manifest for {batch_id}; generated batches: {allowed}")

def checkpoint_error(exc: Exception) -> None:
    typer.echo(f"Error: {exc}", err=True)
    raise typer.Exit(1)

def try_restore_checkpoint(
    *,
    output: Path,
    artifact_root: Path,
    artifact_backend: str = "local",
    hf_repo_id: str | None = None,
    hf_repo_type: str = "dataset",
    hf_revision: str = "main",
    hf_prefix: str = "",
    phase: str,
    batch_id: str | None = None,
    release_id: str | None = None,
) -> bool:
    runtime = runtime_paths()
    resolved_release_id = release_id or runtime.release_id
    store = make_artifact_store_from_env(
        artifact_root=artifact_root,
        backend=artifact_backend,
        hf_repo_id=hf_repo_id,
        hf_repo_type=hf_repo_type,
        hf_revision=hf_revision,
        hf_prefix=hf_prefix,
    )
    relative_path = checkpoint_relative_path(phase, batch_id)
    if not store.exists(relative_path):
        typer.echo(f"No checkpoint found for {relative_path}; continuing.")
        return False
    restore_checkpoint(
        output,
        artifact_root,
        phase,
        batch_id=batch_id,
        release_id=resolved_release_id,
        artifact_backend=artifact_backend,
        hf_repo_id=hf_repo_id,
        hf_repo_type=hf_repo_type,
        hf_revision=hf_revision,
        hf_prefix=hf_prefix,
    )
    typer.echo(f"Restored checkpoint: {relative_path}")
    return True

def save_phase_checkpoint(
    *,
    release: Path,
    artifact_root: Path,
    artifact_backend: str = "local",
    hf_repo_id: str | None = None,
    hf_repo_type: str = "dataset",
    hf_revision: str = "main",
    hf_prefix: str = "",
    phase: str,
    batch_id: str | None = None,
    worker_id: str | None = None,
    status: str = "pass",
) -> Path:
    checkpoint_path = save_checkpoint(
        release,
        artifact_root,
        phase,
        batch_id=batch_id,
        worker_id=worker_id,
        status=status,
        artifact_backend=artifact_backend,
        hf_repo_id=hf_repo_id,
        hf_repo_type=hf_repo_type,
        hf_revision=hf_revision,
        hf_prefix=hf_prefix,
    )
    typer.echo(f"Saved checkpoint: {checkpoint_path}")
    return checkpoint_path

EXPECTED_CHECKPOINT_ERRORS = (
    FileNotFoundError,
    FileExistsError,
    ValueError,
    zipfile.BadZipFile,
    *HF_EXPECTED_ERRORS,
)