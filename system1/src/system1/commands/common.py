from __future__ import annotations

from pathlib import Path

import typer

SUPPORTED_MODES = {"debug_small_sample", "bronze_fast", "silver_balanced", "gold_full"}
SUPPORTED_PROVIDERS = {"mock", "real", "config", "rule_based", "vlm"}
SUPPORTED_BATCHES = {"batch_000"}
RELEASE_NAME = "competition_dataset_v001"


def default_output() -> Path:
    return Path(__file__).resolve().parents[3] / "output"


def release_dir(output: Path) -> Path:
    return output / RELEASE_NAME


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


def require_supported_batch(batch_id: str) -> None:
    if batch_id not in SUPPORTED_BATCHES:
        raise typer.BadParameter("only batch_000 exists in debug_small_sample")
