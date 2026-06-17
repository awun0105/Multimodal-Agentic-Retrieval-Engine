from __future__ import annotations

from pathlib import Path

import typer

from system1.runtime.environment import resolve_runtime_environment
from system1.release.types import release_root

SUPPORTED_MODES = {"debug_small_sample", "bronze_fast", "silver_balanced", "gold_full"}
SUPPORTED_PROVIDERS = {"mock", "real", "config", "rule_based", "vlm"}

def default_output() -> Path:
    return resolve_runtime_environment().output_root


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
